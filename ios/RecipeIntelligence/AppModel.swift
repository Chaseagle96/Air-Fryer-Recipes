import Foundation
import SwiftData

enum FeedRefreshTrigger {
    case manual
    case foreground
    case periodic
}

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var verticals: [RecipeVertical] = []
    @Published var selectedVertical: RecipeVertical?
    @Published private(set) var deck: [RemoteRecipe] = []
    @Published private(set) var isLoading = false
    @Published private(set) var isRefreshingFeed = false
    @Published private(set) var feedStatusMessage: String?
    @Published private(set) var currentFeedGeneratedAt: String?
    @Published private(set) var lastFeedRefreshAt: Date?
    @Published var errorMessage: String?
    @Published private(set) var canUndo = false
    @Published var activeProfileID: UUID?

    private let modelContext: ModelContext
    private let client: any RecipeIntelligenceClient
    private let recommendationService: any RecommendationService
    private let shoppingListService = ShoppingListService()
    private var fetchedRecipes: [RemoteRecipe] = []
    private var nextPageIndex = 0
    private var reachedEnd = false
    private var lastUndo: UndoState?
    private var loadedFeedGeneratedAt: [String: String] = [:]
    private var selectionGeneration = UUID()

    private struct UndoState {
        let recipe: RemoteRecipe
        let eventIDs: [UUID]
        let createdSavedKey: String?
    }

    init(
        modelContext: ModelContext,
        client: any RecipeIntelligenceClient,
        recommendationService: any RecommendationService = MVPRecommendationService()
    ) {
        self.modelContext = modelContext
        self.client = client
        self.recommendationService = recommendationService
    }

    func bootstrap() async {
        ensureDefaultProfile()
        guard verticals.isEmpty else { return }
        do {
            verticals = try await client.fetchVerticals(forceRefresh: true)
        } catch {
            verticals = RecipeVertical.fallbacks
            errorMessage = "The vertical catalog is offline. Using the last-known Recipe Intelligence verticals."
        }
        let preferred = UserDefaults.standard.string(forKey: "selectedVerticalID")
        let initial = verticals.first(where: { $0.id == preferred }) ?? verticals.first
        if let initial { await selectVertical(initial) }
    }

    func selectVertical(_ vertical: RecipeVertical) async {
        guard selectedVertical?.id != vertical.id || fetchedRecipes.isEmpty else { return }
        selectionGeneration = UUID()
        let generation = selectionGeneration
        selectedVertical = vertical
        UserDefaults.standard.set(vertical.id, forKey: "selectedVerticalID")
        fetchedRecipes = []
        deck = []
        nextPageIndex = 0
        reachedEnd = false
        isLoading = false
        currentFeedGeneratedAt = loadedFeedGeneratedAt[vertical.id]
        feedStatusMessage = nil
        errorMessage = nil

        do {
            let manifest = try await client.fetchFeedManifest(vertical: vertical, forceRefresh: true)
            guard generation == selectionGeneration, selectedVertical?.id == vertical.id else { return }
            if manifest.pages.isEmpty {
                loadedFeedGeneratedAt[vertical.id] = manifest.generatedAt
                currentFeedGeneratedAt = manifest.generatedAt
                reachedEnd = true
                lastFeedRefreshAt = .now
                rebuildDeck()
                return
            }
        } catch {
            // loadNextPage can still use a previously cached manifest or the local
            // SwiftData recipe cache, so defer user-facing error handling to it.
        }
        await loadNextPage(generation: generation)
    }

    func retry() async {
        if let selectedVertical {
            selectionGeneration = UUID()
            let generation = selectionGeneration
            fetchedRecipes = []
            deck = []
            nextPageIndex = 0
            reachedEnd = false
            isLoading = false
            feedStatusMessage = nil
            _ = try? await client.fetchFeedManifest(vertical: selectedVertical, forceRefresh: true)
            guard generation == selectionGeneration else { return }
            await loadNextPage(generation: generation)
        } else {
            await bootstrap()
        }
    }

    func refreshCurrentFeed(trigger: FeedRefreshTrigger) async {
        guard !isRefreshingFeed, !isLoading, var vertical = selectedVertical else { return }
        isRefreshingFeed = true
        defer { isRefreshingFeed = false }

        let generation = selectionGeneration
        let pinnedAtStart = deck.first

        // Refresh the catalog too, so newly added verticals appear without an app
        // update or relaunch. A catalog failure should not prevent the current
        // vertical from checking its own feed.
        if let refreshedVerticals = try? await client.fetchVerticals(forceRefresh: true), !refreshedVerticals.isEmpty {
            guard generation == selectionGeneration else { return }
            verticals = refreshedVerticals
            if let refreshedSelection = refreshedVerticals.first(where: { $0.id == vertical.id }) {
                selectedVertical = refreshedSelection
                vertical = refreshedSelection
            }
        }

        do {
            let manifest = try await client.fetchFeedManifest(vertical: vertical, forceRefresh: true)
            guard generation == selectionGeneration, selectedVertical?.id == vertical.id else { return }

            let previousVersion = loadedFeedGeneratedAt[vertical.id]
            lastFeedRefreshAt = .now
            if previousVersion == manifest.generatedAt {
                if trigger == .manual {
                    feedStatusMessage = "Recipe Intelligence is up to date."
                } else {
                    feedStatusMessage = nil
                }
                return
            }

            let pagesToReload = min(max(nextPageIndex, 1), manifest.pages.count)
            var refreshedRecipes: [RemoteRecipe] = []
            if pagesToReload > 0 {
                for pageIndex in 0..<pagesToReload {
                    let page = try await client.fetchRecipePage(vertical: vertical, pageIndex: pageIndex)
                    guard generation == selectionGeneration, selectedVertical?.id == vertical.id else { return }
                    refreshedRecipes.append(contentsOf: page.recipes)
                }
            }

            fetchedRecipes = uniqueRecipes(refreshedRecipes)
            nextPageIndex = pagesToReload
            reachedEnd = pagesToReload >= manifest.pages.count
            loadedFeedGeneratedAt[vertical.id] = manifest.generatedAt
            currentFeedGeneratedAt = manifest.generatedAt
            cache(fetchedRecipes)
            synchronizeSavedMetadata(fetchedRecipes)

            // If the user made a decision while the network request was in flight,
            // do not resurrect that card. Otherwise pin the currently visible card
            // while replacing and re-ranking the unseen pool beneath it.
            let pinnedNow: RemoteRecipe?
            if let pinnedAtStart, deck.first?.recipeID == pinnedAtStart.recipeID {
                pinnedNow = pinnedAtStart
            } else {
                pinnedNow = nil
            }
            rebuildDeck(preserving: pinnedNow)
            errorMessage = nil
            feedStatusMessage = "Rankings updated from Recipe Intelligence."
        } catch {
            if deck.isEmpty { errorMessage = error.localizedDescription }
            feedStatusMessage = "Couldn’t check for new rankings. Showing current recipes."
        }
    }

    func prefetchIfNeeded(_ recipe: RemoteRecipe) async {
        guard !isRefreshingFeed else { return }
        guard let index = deck.firstIndex(where: { $0.recipeID == recipe.recipeID }) else { return }
        if index <= 4 && deck.count < 12 && !reachedEnd {
            await loadNextPage(preservingTop: deck.first, generation: selectionGeneration)
        }
    }

    func handleDecision(_ decision: RecipeDecision, recipe: RemoteRecipe) {
        guard let profileID = activeProfileID else { return }
        var eventIDs: [UUID] = []
        let swipeType: BehaviorEventType = switch decision {
        case .save: .swipeSave
        case .skip: .swipeSkip
        case .notNow: .swipeNotNow
        }
        eventIDs.append(recordEvent(swipeType, recipeID: recipe.recipeID, verticalID: recipe.verticalID))

        var createdSavedKey: String?
        if decision == .save {
            if let created = saveRecipe(recipe, profileID: profileID, recordEvent: true) {
                createdSavedKey = created.key
                if let savedEvent = latestEventID(type: .recipeSaved, recipeID: recipe.recipeID) { eventIDs.append(savedEvent) }
            }
        }

        deck.removeAll { $0.recipeID == recipe.recipeID }
        lastUndo = UndoState(recipe: recipe, eventIDs: eventIDs, createdSavedKey: createdSavedKey)
        canUndo = true
        recordImpressionForTopCard()
    }

    func undoLastDecision() {
        guard let lastUndo, let profileID = activeProfileID else { return }
        let events = fetchAll(BehaviorEventRecord.self)
        for event in events where lastUndo.eventIDs.contains(event.id) { event.isUndone = true }
        if let key = lastUndo.createdSavedKey,
           let saved = fetchAll(SavedRecipeRecord.self).first(where: { $0.key == key }) {
            modelContext.delete(saved)
        }
        _ = recordEvent(.undoSwipe, recipeID: lastUndo.recipe.recipeID, verticalID: lastUndo.recipe.verticalID, profileID: profileID)
        deck.insert(lastUndo.recipe, at: 0)
        self.lastUndo = nil
        canUndo = false
        try? modelContext.save()
    }

    func saveFromDetail(_ recipe: RemoteRecipe) {
        guard let profileID = activeProfileID else { return }
        _ = saveRecipe(recipe, profileID: profileID, recordEvent: true)
    }

    func recordOpened(_ recipe: RemoteRecipe) {
        _ = recordEvent(.recipeOpened, recipeID: recipe.recipeID, verticalID: recipe.verticalID)
    }

    func recordOriginalSourceOpened(recipeID: String, verticalID: String) {
        _ = recordEvent(.originalSourceOpened, recipeID: recipeID, verticalID: verticalID)
    }

    @discardableResult
    func recordEvent(
        _ type: BehaviorEventType,
        recipeID: String,
        verticalID: String,
        profileID: UUID? = nil,
        context: [String: String] = [:]
    ) -> UUID {
        let profile = profileID ?? activeProfileID ?? ensureDefaultProfile()
        let event = BehaviorEventRecord(profileID: profile, recipeID: recipeID, verticalID: verticalID, eventType: type, context: context)
        modelContext.insert(event)
        try? modelContext.save()
        return event.id
    }

    func addNote(to saved: SavedRecipeRecord, text: String) {
        guard let profileID = activeProfileID else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        modelContext.insert(PersonalNoteRecord(profileID: profileID, recipeID: saved.recipeID, text: trimmed))
        _ = recordEvent(.noteAdded, recipeID: saved.recipeID, verticalID: saved.verticalID)
        try? modelContext.save()
    }

    func markCooked(_ saved: SavedRecipeRecord) {
        guard let profileID = activeProfileID else { return }
        let priorCount = fetchAll(CookingEventRecord.self).filter { $0.profileID == profileID && $0.recipeID == saved.recipeID }.count
        modelContext.insert(CookingEventRecord(profileID: profileID, recipeID: saved.recipeID))
        if saved.status != .favorite { saved.status = .cooked }
        _ = recordEvent(priorCount == 0 ? .recipeCooked : .recipeCookedAgain, recipeID: saved.recipeID, verticalID: saved.verticalID)
        try? modelContext.save()
    }

    func submitReview(
        for saved: SavedRecipeRecord,
        overall: Int,
        taste: Int,
        ease: Int,
        value: Int,
        wouldMakeAgain: WouldMakeAgain,
        householdReaction: String,
        notes: String
    ) {
        guard let profileID = activeProfileID else { return }
        modelContext.insert(PersonalReviewRecord(
            profileID: profileID,
            recipeID: saved.recipeID,
            overall: overall,
            taste: taste,
            ease: ease,
            value: value,
            wouldMakeAgain: wouldMakeAgain,
            householdReaction: householdReaction,
            notes: notes
        ))
        _ = recordEvent(.personalReviewSubmitted, recipeID: saved.recipeID, verticalID: saved.verticalID)
        try? modelContext.save()
    }

    func toggleFavorite(_ saved: SavedRecipeRecord) {
        saved.status = saved.status == .favorite ? .cooked : .favorite
        if saved.status == .favorite { _ = recordEvent(.recipeFavorited, recipeID: saved.recipeID, verticalID: saved.verticalID) }
        try? modelContext.save()
    }

    func setStatus(_ status: SavedRecipeStatus, for saved: SavedRecipeRecord) {
        saved.status = status
        try? modelContext.save()
    }

    func planRecipe(_ saved: SavedRecipeRecord, on date: Date) {
        guard let profileID = activeProfileID else { return }
        let calendar = Calendar.current
        let day = calendar.startOfDay(for: date)
        for entry in fetchAll(MealPlanEntry.self) where entry.profileID == profileID && calendar.isDate(entry.date, inSameDayAs: day) {
            modelContext.delete(entry)
        }
        modelContext.insert(MealPlanEntry(profileID: profileID, saved: saved, date: day))
        if saved.status == .wantToTry { saved.status = .planned }
        _ = recordEvent(.recipePlanned, recipeID: saved.recipeID, verticalID: saved.verticalID, context: ["date": ISO8601DateFormatter().string(from: day)])
        try? modelContext.save()
    }

    func unplan(_ entry: MealPlanEntry) {
        _ = recordEvent(.recipeUnplanned, recipeID: entry.recipeID, verticalID: entry.verticalID)
        modelContext.delete(entry)
        try? modelContext.save()
    }

    func generateShoppingList() {
        guard let profileID = activeProfileID else { return }
        let now = Calendar.current.startOfDay(for: .now)
        let end = Calendar.current.date(byAdding: .day, value: 7, to: now) ?? now
        let plans = fetchAll(MealPlanEntry.self).filter { $0.profileID == profileID && $0.date >= now && $0.date < end }
        let recipeIDs = Set(plans.map(\.recipeID))
        let saved = fetchAll(SavedRecipeRecord.self).filter { $0.profileID == profileID && recipeIDs.contains($0.recipeID) }
        for item in fetchAll(ShoppingListItem.self) where item.profileID == profileID && !item.isManual { modelContext.delete(item) }
        let drafts = shoppingListService.combine(savedRecipes: saved)
        for draft in drafts { modelContext.insert(ShoppingListItem(profileID: profileID, draft: draft)) }
        for savedRecord in saved {
            _ = recordEvent(.shoppingListAdded, recipeID: savedRecord.recipeID, verticalID: savedRecord.verticalID)
        }
        try? modelContext.save()
    }

    func addManualShoppingItem(_ text: String) {
        guard let profileID = activeProfileID else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let draft = IngredientParser.parse(trimmed, recipeID: "manual")
        modelContext.insert(ShoppingListItem(profileID: profileID, draft: draft, isManual: true))
        try? modelContext.save()
    }

    func deleteShoppingItem(_ item: ShoppingListItem) {
        modelContext.delete(item)
        try? modelContext.save()
    }

    func addProfile(named name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let profile = UserProfileRecord(displayName: trimmed)
        modelContext.insert(profile)
        let household = fetchAll(HouseholdRecord.self).first ?? HouseholdRecord()
        if household.modelContext == nil { modelContext.insert(household) }
        var members = household.memberIDs
        members.append(profile.id)
        household.memberIDs = Array(Set(members))
        try? modelContext.save()
    }

    func setActiveProfile(_ profile: UserProfileRecord) {
        activeProfileID = profile.id
        UserDefaults.standard.set(profile.id.uuidString, forKey: "activeProfileID")
        rebuildDeck()
    }

    private func loadNextPage(preservingTop: RemoteRecipe? = nil, generation: UUID? = nil) async {
        let requestGeneration = generation ?? selectionGeneration
        guard requestGeneration == selectionGeneration else { return }
        guard !isLoading, !reachedEnd, let vertical = selectedVertical else { return }
        isLoading = true
        defer {
            if requestGeneration == selectionGeneration { isLoading = false }
        }
        do {
            let page = try await client.fetchRecipePage(vertical: vertical, pageIndex: nextPageIndex)
            guard requestGeneration == selectionGeneration, selectedVertical?.id == vertical.id else { return }
            nextPageIndex += 1
            reachedEnd = page.recipes.isEmpty
            loadedFeedGeneratedAt[vertical.id] = page.generatedAt
            currentFeedGeneratedAt = page.generatedAt
            lastFeedRefreshAt = .now
            let existing = Set(fetchedRecipes.map(\.recipeID))
            let fresh = page.recipes.filter { !existing.contains($0.recipeID) }
            fetchedRecipes.append(contentsOf: fresh)
            cache(fresh)
            synchronizeSavedMetadata(fresh)
            rebuildDeck(preserving: preservingTop)
            errorMessage = nil
            if deck.count < 8 && !reachedEnd {
                await loadNextPage(preservingTop: deck.first, generation: requestGeneration)
            }
        } catch RecipeIntelligenceClientError.pageOutOfRange {
            guard requestGeneration == selectionGeneration else { return }
            reachedEnd = true
        } catch {
            guard requestGeneration == selectionGeneration, selectedVertical?.id == vertical.id else { return }
            let cached = cachedRecipes(verticalID: vertical.id)
            if fetchedRecipes.isEmpty && !cached.isEmpty {
                fetchedRecipes = cached
                reachedEnd = true
                rebuildDeck(preserving: preservingTop)
                errorMessage = "Offline: showing cached recipes."
            } else {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func rebuildDeck(preserving pinnedRecipe: RemoteRecipe? = nil) {
        guard let profileID = activeProfileID else {
            deck = fetchedRecipes
            return
        }
        let saved = Set(fetchAll(SavedRecipeRecord.self).filter { $0.profileID == profileID && $0.status != .archived }.map(\.recipeID))
        let events = fetchAll(BehaviorEventRecord.self).filter { $0.profileID == profileID && !$0.isUndone }
        let skipped = Set(events.filter { $0.eventType == .swipeSkip }.map(\.recipeID))
        let notNowCutoff = Date.now.addingTimeInterval(-24 * 3600)
        let notNow = Set(events.filter { $0.eventType == .swipeNotNow && $0.timestamp >= notNowCutoff }.map(\.recipeID))
        var recommendations = recommendationService.recommendations(
            from: fetchedRecipes,
            signals: RecommendationSignals(savedRecipeIDs: saved, skippedRecipeIDs: skipped, notNowRecipeIDs: notNow)
        )

        if let pinnedRecipe,
           !saved.contains(pinnedRecipe.recipeID),
           !skipped.contains(pinnedRecipe.recipeID),
           !notNow.contains(pinnedRecipe.recipeID) {
            if let freshIndex = recommendations.firstIndex(where: { $0.recipeID == pinnedRecipe.recipeID }) {
                let refreshedPinned = recommendations.remove(at: freshIndex)
                recommendations.insert(refreshedPinned, at: 0)
            } else {
                recommendations.insert(pinnedRecipe, at: 0)
            }
        }

        deck = recommendations
        recordImpressionForTopCard()
    }

    private func saveRecipe(_ recipe: RemoteRecipe, profileID: UUID, recordEvent shouldRecord: Bool) -> SavedRecipeRecord? {
        if fetchAll(SavedRecipeRecord.self).contains(where: { $0.profileID == profileID && $0.recipeID == recipe.recipeID }) { return nil }
        let saved = SavedRecipeRecord(recipe: recipe, profileID: profileID)
        modelContext.insert(saved)
        if shouldRecord { _ = recordEvent(.recipeSaved, recipeID: recipe.recipeID, verticalID: recipe.verticalID, profileID: profileID) }
        try? modelContext.save()
        return saved
    }

    private func latestEventID(type: BehaviorEventType, recipeID: String) -> UUID? {
        fetchAll(BehaviorEventRecord.self)
            .filter { $0.eventType == type && $0.recipeID == recipeID }
            .max(by: { $0.timestamp < $1.timestamp })?.id
    }

    private func recordImpressionForTopCard() {
        guard let top = deck.first else { return }
        _ = recordEvent(.recipeImpression, recipeID: top.recipeID, verticalID: top.verticalID)
    }

    private func cache(_ recipes: [RemoteRecipe]) {
        guard !recipes.isEmpty else { return }
        let existing = Dictionary(uniqueKeysWithValues: fetchAll(RecipeCacheRecord.self).map { ($0.cacheKey, $0) })
        for recipe in recipes {
            let key = "\(recipe.verticalID)|\(recipe.recipeID)"
            if let record = existing[key], let data = try? JSONEncoder().encode(recipe), let text = String(data: data, encoding: .utf8) {
                record.payloadJSON = text
                record.cachedAt = .now
            } else {
                modelContext.insert(RecipeCacheRecord(recipe: recipe))
            }
        }
        try? modelContext.save()
    }

    private func synchronizeSavedMetadata(_ recipes: [RemoteRecipe]) {
        guard !recipes.isEmpty else { return }
        let recipesByKey = Dictionary(uniqueKeysWithValues: recipes.map { ("\($0.verticalID)|\($0.recipeID)", $0) })
        var changed = false
        for saved in fetchAll(SavedRecipeRecord.self) {
            let key = "\(saved.verticalID)|\(saved.recipeID)"
            if let recipe = recipesByKey[key] {
                saved.updateRemoteMetadata(from: recipe)
                changed = true
            }
        }
        if changed { try? modelContext.save() }
    }

    private func uniqueRecipes(_ recipes: [RemoteRecipe]) -> [RemoteRecipe] {
        var seen: Set<String> = []
        return recipes.filter { seen.insert("\($0.verticalID)|\($0.recipeID)").inserted }
    }

    private func cachedRecipes(verticalID: String) -> [RemoteRecipe] {
        fetchAll(RecipeCacheRecord.self)
            .filter { $0.verticalID == verticalID }
            .compactMap(\.recipe)
            .sorted { $0.rank < $1.rank }
    }

    @discardableResult
    private func ensureDefaultProfile() -> UUID {
        let profiles = fetchAll(UserProfileRecord.self)
        if let stored = UserDefaults.standard.string(forKey: "activeProfileID").flatMap(UUID.init(uuidString:)),
           profiles.contains(where: { $0.id == stored }) {
            activeProfileID = stored
            return stored
        }
        if let first = profiles.first {
            activeProfileID = first.id
            return first.id
        }
        let profile = UserProfileRecord(displayName: "You")
        modelContext.insert(profile)
        let household = HouseholdRecord(memberIDs: [profile.id])
        modelContext.insert(household)
        try? modelContext.save()
        activeProfileID = profile.id
        UserDefaults.standard.set(profile.id.uuidString, forKey: "activeProfileID")
        return profile.id
    }

    private func fetchAll<T: PersistentModel>(_ type: T.Type) -> [T] {
        (try? modelContext.fetch(FetchDescriptor<T>())) ?? []
    }
}
