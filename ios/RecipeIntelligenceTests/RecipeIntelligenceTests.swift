import SwiftData
import XCTest
@testable import RecipeIntelligence

@MainActor
final class RecipeIntelligenceTests: XCTestCase {
    func testVerticalCatalogDecodesBackendContract() throws {
        let json = """
        {"schema_version":1,"verticals":[{"id":"air_fryer","name":"Air Fryer","icon":"wind","available":true,"manifest_url":"https://example.com/manifest.json"}]}
        """
        let catalog = try JSONDecoder().decode(VerticalCatalog.self, from: Data(json.utf8))
        XCTAssertEqual(catalog.schemaVersion, 1)
        XCTAssertEqual(catalog.verticals.first?.id, "air_fryer")
        XCTAssertEqual(catalog.verticals.first?.manifestURL.absoluteString, "https://example.com/manifest.json")
    }

    func testRecipePageDecodesRankingAndIngredientSignals() throws {
        let json = """
        {"schema_version":1,"generated_at":"now","vertical_id":"air_fryer","vertical_name":"Air Fryer","page":1,"recipes":[{"recipe_id":"r1","vertical_id":"air_fryer","vertical_name":"Air Fryer","title":"Air Fryer Chicken","source":"example.com","combined_sources":"example.com","url":"https://example.com/r1","canonical_url":"https://example.com/r1","image_url":"https://example.com/r1.jpg","author":"Chef","categories":["Chicken"],"ingredients":["1 onion"],"has_instructions":true,"instruction_count":5,"rank":1,"rating":4.9,"rating_count":1200,"hierarchical_score":4.7,"evidence_confidence":0.95,"evidence_grade":"A","evidence_status":"verified","rank_confidence":0.91,"rank_range_low":1,"rank_range_high":3,"rank_provenance":"test"}]}
        """
        let page = try JSONDecoder().decode(RecipePageEnvelope.self, from: Data(json.utf8))
        let recipe = try XCTUnwrap(page.recipes.first)
        XCTAssertEqual(recipe.rank, 1)
        XCTAssertEqual(recipe.ingredients, ["1 onion"])
        XCTAssertEqual(recipe.photoURL?.absoluteString, "https://example.com/r1.jpg")
        XCTAssertTrue(recipe.isGloballyRanked, "Older ranked pages remain discoverable when corpus metadata is absent.")
    }

    func testManifestDecodesCompleteCorpusMetadata() throws {
        let json = """
        {"schema_version":1,"generated_at":"v2","vertical":{"id":"air_fryer","name":"Air Fryer","source_count":40},"recipe_count":1068,"ranked_recipe_count":1068,"page_size":100,"pages":[{"index":1,"path":"recipes/0001.json","count":100}],"corpus_recipe_count":1842,"corpus_pages":[{"index":1,"path":"corpus/0001.json","count":100},{"index":2,"path":"corpus/0002.json","count":100}],"corpus_status_counts":{"discover":1068,"explore":510,"archive":240,"suppressed":24},"catalog_url_count":3744}
        """
        let manifest = try JSONDecoder().decode(FeedManifest.self, from: Data(json.utf8))
        XCTAssertEqual(manifest.effectiveRankedRecipeCount, 1068)
        XCTAssertEqual(manifest.effectiveCorpusRecipeCount, 1842)
        XCTAssertEqual(manifest.effectiveCorpusPages.first?.path, "corpus/0001.json")
        XCTAssertEqual(manifest.corpusStatusCounts?["explore"], 510)
        XCTAssertEqual(manifest.catalogURLCount, 3744)
    }

    func testCorpusRecipeDecodesServeabilityWithoutFakeRank() throws {
        let json = """
        {"schema_version":1,"generated_at":"v2","vertical_id":"air_fryer","vertical_name":"Air Fryer","page":1,"recipes":[{"recipe_id":"r2","vertical_id":"air_fryer","vertical_name":"Air Fryer","title":"Unranked Chicken","source":"example.com","combined_sources":"example.com","url":"https://example.com/r2","canonical_url":"https://example.com/r2","image_url":"https://example.com/r2.jpg","author":"Chef","categories":["Chicken"],"ingredients":["1 onion"],"has_instructions":true,"instruction_count":5,"rank":0,"rating":4.8,"rating_count":0,"hierarchical_score":0.0,"evidence_confidence":0.4,"evidence_grade":"","evidence_status":"schema_only","rank_confidence":0.0,"rank_range_low":null,"rank_range_high":null,"rank_provenance":"","is_ranked":false,"discover_eligible":false,"explore_eligible":true,"serveability":"explore","status_reasons":["no_rating_evidence","low_evidence"],"last_seen_at":"2026-08-19T00:00:00Z"}]}
        """
        let page = try JSONDecoder().decode(RecipePageEnvelope.self, from: Data(json.utf8))
        let recipe = try XCTUnwrap(page.recipes.first)
        XCTAssertFalse(recipe.isGloballyRanked)
        XCTAssertFalse(recipe.isDiscoverEligible)
        XCTAssertTrue(recipe.isExploreEligible)
        XCTAssertEqual(recipe.serveability, "explore")
        XCTAssertEqual(recipe.rankingLabel, "Exploratory · Air Fryer")
        XCTAssertEqual(recipe.statusReasons ?? [], ["no_rating_evidence", "low_evidence"])
    }

    func testRecommendationFiltersSavedSkippedAndNotNow() {
        let recipes = SampleData.recipes.filter { $0.verticalID == "air_fryer" }
        let service = MVPRecommendationService()
        let output = service.recommendations(
            from: recipes,
            signals: RecommendationSignals(
                savedRecipeIDs: ["af-chicken"],
                skippedRecipeIDs: ["af-potatoes"],
                notNowRecipeIDs: ["af-salmon"]
            )
        )
        XCTAssertEqual(output.map(\.recipeID), ["af-broccoli"])
    }

    func testShoppingListMergesCompatibleQuantities() {
        let profileID = UUID()
        let roast = SavedRecipeRecord(recipe: SampleData.recipes.first(where: { $0.recipeID == "sc-roast" })!, profileID: profileID)
        let ribs = SavedRecipeRecord(recipe: SampleData.recipes.first(where: { $0.recipeID == "sc-ribs" })!, profileID: profileID)
        let drafts = ShoppingListService().combine(savedRecipes: [roast, ribs])
        let onion = drafts.first(where: { $0.normalizedKey.hasPrefix("onion|") })
        XCTAssertEqual(onion?.amount, 3)
        XCTAssertEqual(Set(onion?.sourceRecipeIDs ?? []), Set(["sc-roast", "sc-ribs"]))
    }

    func testSaveUndoAndEventHistoryPersist() async throws {
        let container = try makeContainer()
        let context = container.mainContext
        let model = AppModel(modelContext: context, client: PreviewRecipeIntelligenceClient())
        await model.bootstrap()
        let first = try XCTUnwrap(model.deck.first)
        model.handleDecision(.save, recipe: first)

        var saved = try context.fetch(FetchDescriptor<SavedRecipeRecord>())
        var events = try context.fetch(FetchDescriptor<BehaviorEventRecord>())
        XCTAssertEqual(saved.count, 1)
        XCTAssertTrue(events.contains(where: { $0.eventType == .swipeSave }))
        XCTAssertTrue(events.contains(where: { $0.eventType == .recipeSaved }))

        model.undoLastDecision()
        saved = try context.fetch(FetchDescriptor<SavedRecipeRecord>())
        events = try context.fetch(FetchDescriptor<BehaviorEventRecord>())
        XCTAssertTrue(saved.isEmpty)
        XCTAssertTrue(events.contains(where: { $0.eventType == .undoSwipe }))
        XCTAssertEqual(model.deck.first?.recipeID, first.recipeID)
    }

    func testMealPlanningAndShoppingGeneration() async throws {
        let container = try makeContainer()
        let context = container.mainContext
        let model = AppModel(modelContext: context, client: PreviewRecipeIntelligenceClient())
        await model.bootstrap()
        let first = try XCTUnwrap(model.deck.first)
        model.saveFromDetail(first)
        let saved = try XCTUnwrap(context.fetch(FetchDescriptor<SavedRecipeRecord>()).first)
        model.planRecipe(saved, on: .now)
        model.generateShoppingList()
        let plans = try context.fetch(FetchDescriptor<MealPlanEntry>())
        let shopping = try context.fetch(FetchDescriptor<ShoppingListItem>())
        XCTAssertEqual(plans.count, 1)
        XCTAssertFalse(shopping.isEmpty)
    }

    func testFeedRefreshPinsVisibleCardAndRefreshesSavedMetadata() async throws {
        let visibleV1 = makeRecipe(id: "visible", title: "Visible Recipe", rank: 1, score: 4.90, rating: 4.8, ratingCount: 100)
        let savedV1 = makeRecipe(id: "saved", title: "Saved Recipe", rank: 2, score: 4.60, rating: 4.6, ratingCount: 40)
        let client = RefreshingTestClient(version: "v1", recipes: [visibleV1, savedV1])
        let container = try makeContainer()
        let context = container.mainContext
        let model = AppModel(modelContext: context, client: client)

        await model.bootstrap()
        XCTAssertEqual(model.currentFeedGeneratedAt, "v1")
        XCTAssertEqual(model.deck.first?.recipeID, "visible")
        model.saveFromDetail(savedV1)

        let newLeader = makeRecipe(id: "new", title: "New Leader", rank: 1, score: 5.00, rating: 4.9, ratingCount: 900)
        let visibleV2 = makeRecipe(id: "visible", title: "Visible Recipe", rank: 2, score: 4.80, rating: 4.8, ratingCount: 130)
        let savedV2 = makeRecipe(id: "saved", title: "Saved Recipe", rank: 3, score: 4.55, rating: 4.7, ratingCount: 75)
        await client.advance(version: "v2", recipes: [newLeader, visibleV2, savedV2])

        await model.refreshCurrentFeed(trigger: .manual)

        XCTAssertEqual(model.currentFeedGeneratedAt, "v2")
        XCTAssertEqual(model.deck.first?.recipeID, "visible", "The card already under the user's finger should stay in place.")
        XCTAssertEqual(model.deck.first?.rank, 2, "Pinned cards should still receive fresh ranking metadata.")
        XCTAssertTrue(model.deck.dropFirst().contains(where: { $0.recipeID == "new" }))
        XCTAssertEqual(model.feedStatusMessage, "Rankings updated from Recipe Intelligence.")

        let saved = try XCTUnwrap(context.fetch(FetchDescriptor<SavedRecipeRecord>()).first(where: { $0.recipeID == "saved" }))
        XCTAssertEqual(saved.status, .wantToTry, "Remote refreshes must not rewrite personal lifecycle state.")
        XCTAssertEqual(saved.rank, 3)
        XCTAssertEqual(saved.rating, 4.7)
        XCTAssertEqual(saved.ratingCount, 75)
    }

    func testManualRefreshReportsUnchangedFeedWithoutReordering() async throws {
        let first = makeRecipe(id: "first", title: "First", rank: 1, score: 4.9, rating: 4.8, ratingCount: 100)
        let second = makeRecipe(id: "second", title: "Second", rank: 2, score: 4.7, rating: 4.7, ratingCount: 80)
        let client = RefreshingTestClient(version: "same", recipes: [first, second])
        let container = try makeContainer()
        let model = AppModel(modelContext: container.mainContext, client: client)

        await model.bootstrap()
        let before = model.deck.map(\.recipeID)
        await model.refreshCurrentFeed(trigger: .manual)

        XCTAssertEqual(model.deck.map(\.recipeID), before)
        XCTAssertEqual(model.feedStatusMessage, "Recipe Intelligence is up to date.")
        XCTAssertNotNil(model.lastFeedRefreshAt)
    }

    private func makeContainer() throws -> ModelContainer {
        let schema = Schema([
            RecipeCacheRecord.self,
            UserProfileRecord.self,
            HouseholdRecord.self,
            SavedRecipeRecord.self,
            BehaviorEventRecord.self,
            PersonalNoteRecord.self,
            PersonalReviewRecord.self,
            CookingEventRecord.self,
            MealPlanEntry.self,
            ShoppingListItem.self
        ])
        return try ModelContainer(for: schema, configurations: [ModelConfiguration(schema: schema, isStoredInMemoryOnly: true)])
    }

    private func makeRecipe(
        id: String,
        title: String,
        rank: Int,
        score: Double,
        rating: Double,
        ratingCount: Int
    ) -> RemoteRecipe {
        RemoteRecipe(
            recipeID: id,
            verticalID: "air_fryer",
            verticalName: "Air Fryer",
            title: title,
            source: "example.com",
            combinedSources: "example.com",
            url: "https://example.com/\(id)",
            canonicalURL: "https://example.com/\(id)",
            imageURL: "https://example.com/\(id).jpg",
            author: "Chef",
            categories: ["Dinner"],
            ingredients: ["1 onion"],
            hasInstructions: true,
            instructionCount: 4,
            rank: rank,
            rating: rating,
            ratingCount: ratingCount,
            hierarchicalScore: score,
            evidenceConfidence: 0.9,
            evidenceGrade: "A",
            evidenceStatus: "verified",
            rankConfidence: 0.95,
            rankRangeLow: rank,
            rankRangeHigh: rank,
            rankProvenance: "test"
        )
    }
}

private actor RefreshingTestClient: RecipeIntelligenceClient {
    private var version: String
    private var recipes: [RemoteRecipe]
    private let vertical = RecipeVertical(
        id: "air_fryer",
        name: "Air Fryer",
        icon: "wind",
        available: true,
        manifestURL: URL(string: "https://example.com/manifest.json")!
    )

    init(version: String, recipes: [RemoteRecipe]) {
        self.version = version
        self.recipes = recipes
    }

    func advance(version: String, recipes: [RemoteRecipe]) {
        self.version = version
        self.recipes = recipes
    }

    func fetchVerticals(forceRefresh: Bool) async throws -> [RecipeVertical] {
        [vertical]
    }

    func fetchFeedManifest(vertical: RecipeVertical, forceRefresh: Bool) async throws -> FeedManifest {
        FeedManifest(
            schemaVersion: 1,
            generatedAt: version,
            vertical: FeedVerticalDescriptor(id: vertical.id, name: vertical.name, sourceCount: 1),
            recipeCount: recipes.count,
            pageSize: max(recipes.count, 1),
            pages: recipes.isEmpty ? [] : [FeedPageReference(index: 1, path: "recipes/0001.json", count: recipes.count)]
        )
    }

    func fetchRecipePage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope {
        guard pageIndex == 0 else { throw RecipeIntelligenceClientError.pageOutOfRange }
        return RecipePageEnvelope(
            schemaVersion: 1,
            generatedAt: version,
            verticalID: vertical.id,
            verticalName: vertical.name,
            page: 1,
            recipes: recipes
        )
    }
}
