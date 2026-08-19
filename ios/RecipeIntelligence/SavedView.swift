import SwiftData
import SwiftUI

struct SavedView: View {
    @EnvironmentObject private var appModel: AppModel
    @Query(sort: \SavedRecipeRecord.savedAt, order: .reverse) private var allSaved: [SavedRecipeRecord]
    @State private var searchText = ""
    @State private var statusFilter = "All"
    @State private var verticalFilter = "All"
    @State private var showPicker = false

    private var saved: [SavedRecipeRecord] {
        allSaved.filter { record in
            guard record.profileID == appModel.activeProfileID else { return false }
            let matchesSearch = searchText.isEmpty || record.title.localizedCaseInsensitiveContains(searchText) || record.source.localizedCaseInsensitiveContains(searchText)
            let matchesStatus = statusFilter == "All" || record.status.rawValue == statusFilter
            let matchesVertical = verticalFilter == "All" || record.verticalName == verticalFilter
            return matchesSearch && matchesStatus && matchesVertical
        }
    }

    var body: some View {
        Group {
            if saved.isEmpty {
                ContentUnavailableView("No saved recipes yet", systemImage: "heart", description: Text("Swipe right in Discover when something looks worth trying."))
            } else {
                List {
                    Section {
                        Button("Help Me Pick", systemImage: "shuffle") { showPicker = true }
                            .disabled(saved.filter { $0.status == .wantToTry }.count < 2)
                    }
                    ForEach(saved) { record in
                        NavigationLink {
                            SavedRecipeDetailView(saved: record)
                        } label: {
                            SavedRecipeRow(saved: record)
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
        }
        .recipeScreenBackground()
        .navigationTitle("Saved")
        .searchable(text: $searchText, prompt: "Search saved recipes")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu("Filter", systemImage: "line.3.horizontal.decrease.circle") {
                    Picker("Status", selection: $statusFilter) {
                        Text("All statuses").tag("All")
                        ForEach(SavedRecipeStatus.allCases) { Text($0.rawValue).tag($0.rawValue) }
                    }
                    Picker("Vertical", selection: $verticalFilter) {
                        Text("All verticals").tag("All")
                        ForEach(Array(Set(allSaved.map(\.verticalName))).sorted(), id: \.self) { Text($0).tag($0) }
                    }
                }
            }
        }
        .sheet(isPresented: $showPicker) {
            NavigationStack {
                EliminationView(recipes: saved.filter { $0.status == .wantToTry })
            }
        }
        .recipeToolbarBehavior()
    }
}

private struct SavedRecipeRow: View {
    let saved: SavedRecipeRecord

    var body: some View {
        HStack(spacing: 12) {
            RemoteRecipeImage(url: saved.imageURL, title: saved.title)
                .frame(width: 78, height: 78)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            VStack(alignment: .leading, spacing: 5) {
                Text(saved.title).font(.headline).lineLimit(2)
                Text("#\(saved.rank) \(saved.verticalName) · \(saved.rating, specifier: "%.1f") ★")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Text(saved.status.rawValue)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
    }
}

struct SavedRecipeDetailView: View {
    @EnvironmentObject private var appModel: AppModel
    @Environment(\.openURL) private var openURL
    @Query(sort: \PersonalNoteRecord.createdAt, order: .reverse) private var allNotes: [PersonalNoteRecord]
    @Query(sort: \PersonalReviewRecord.createdAt, order: .reverse) private var allReviews: [PersonalReviewRecord]
    let saved: SavedRecipeRecord
    @State private var noteText = ""
    @State private var showReview = false
    @State private var showPlan = false
    @State private var planDate = Date.now

    private var notes: [PersonalNoteRecord] { allNotes.filter { $0.recipeID == saved.recipeID && $0.profileID == appModel.activeProfileID } }
    private var reviews: [PersonalReviewRecord] { allReviews.filter { $0.recipeID == saved.recipeID && $0.profileID == appModel.activeProfileID } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                RemoteRecipeImage(url: saved.imageURL, title: saved.title)
                    .frame(height: 290)
                    .clipped()
                    .clipShape(RoundedRectangle(cornerRadius: RecipeDesign.cornerRadius, style: .continuous))

                VStack(alignment: .leading, spacing: 10) {
                    Text(saved.title).font(.largeTitle.bold())
                    Text("#\(saved.rank) \(saved.verticalName) · \(saved.rating, specifier: "%.1f") ★ · \(saved.ratingCount.formatted()) ratings")
                        .foregroundStyle(.secondary)

                    Picker("Status", selection: Binding(
                        get: { saved.status },
                        set: { appModel.setStatus($0, for: saved) }
                    )) {
                        ForEach(SavedRecipeStatus.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.menu)
                }
                .padding(18)
                .frame(maxWidth: .infinity, alignment: .leading)
                .recipeGlassSurface()

                RecipeGlassGroup(spacing: 12) {
                    HStack(spacing: 12) {
                        Button("Plan", systemImage: "calendar.badge.plus") { showPlan = true }
                            .recipeGlassButton()
                        Button("I Cooked This", systemImage: "fork.knife") {
                            appModel.markCooked(saved)
                            showReview = true
                        }
                        .recipeGlassButton(prominent: true)
                        Button(saved.status == .favorite ? "Unfavorite" : "Favorite", systemImage: "heart.fill") { appModel.toggleFavorite(saved) }
                            .recipeGlassButton()
                    }
                }

                if !saved.ingredients.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        sectionTitle("Ingredients", systemImage: "carrot")
                        ForEach(Array(saved.ingredients.enumerated()), id: \.offset) { _, ingredient in
                            Text("• \(ingredient)")
                        }
                    }
                }

                VStack(alignment: .leading, spacing: 12) {
                    sectionTitle("Private notes", systemImage: "note.text")
                    HStack(alignment: .bottom) {
                        TextField("What would you change next time?", text: $noteText, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                        Button("Add") {
                            appModel.addNote(to: saved, text: noteText)
                            noteText = ""
                        }
                        .recipeGlassButton(prominent: true)
                    }
                    ForEach(notes) { note in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(note.text)
                            Text(note.createdAt, format: .dateTime.month().day().year())
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }

                if let latest = reviews.first {
                    VStack(alignment: .leading, spacing: 8) {
                        sectionTitle("Your latest review", systemImage: "star.bubble")
                        Text("Overall \(latest.overall)/5 · Taste \(latest.taste)/5 · Ease \(latest.ease)/5 · Value \(latest.value)/5")
                        Text("Make again: \(latest.wouldMakeAgain.rawValue)")
                        if !latest.householdReaction.isEmpty { Text("Household: \(latest.householdReaction)") }
                        if !latest.notes.isEmpty { Text(latest.notes).foregroundStyle(.secondary) }
                    }
                    .padding(16)
                    .recipeGlassSurface(cornerRadius: RecipeDesign.compactCornerRadius)
                }

                if let url = saved.sourceURL {
                    Button("View Original Recipe", systemImage: "arrow.up.right.square") {
                        appModel.recordOriginalSourceOpened(recipeID: saved.recipeID, verticalID: saved.verticalID)
                        openURL(url)
                    }
                    .recipeGlassButton()
                }
            }
            .padding()
        }
        .recipeScreenBackground()
        .navigationTitle("Saved Recipe")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showReview) { ReviewFormView(saved: saved) }
        .sheet(isPresented: $showPlan) {
            NavigationStack {
                Form {
                    DatePicker("Cook on", selection: $planDate, displayedComponents: .date)
                    Button("Add to Plan") {
                        appModel.planRecipe(saved, on: planDate)
                        showPlan = false
                    }
                }
                .navigationTitle("Plan Recipe")
            }
        }
        .recipeToolbarBehavior()
    }

    private func sectionTitle(_ title: String, systemImage: String) -> some View {
        Label(title, systemImage: systemImage)
            .font(.title2.bold())
            .accessibilityAddTraits(.isHeader)
    }
}
