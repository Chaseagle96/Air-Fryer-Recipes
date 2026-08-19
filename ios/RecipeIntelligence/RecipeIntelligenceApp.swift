import SwiftData
import SwiftUI

@main
@MainActor
struct RecipeIntelligenceApp: App {
    private let modelContainer: ModelContainer
    @StateObject private var appModel: AppModel

    init() {
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
        let isUITesting = ProcessInfo.processInfo.arguments.contains("--ui-testing")
        let configuration = ModelConfiguration(schema: schema, isStoredInMemoryOnly: isUITesting)
        do {
            modelContainer = try ModelContainer(for: schema, configurations: [configuration])
        } catch {
            fatalError("Unable to create Recipe Intelligence data store: \(error)")
        }
        let client: any RecipeIntelligenceClient = isUITesting ? PreviewRecipeIntelligenceClient() : LiveRecipeIntelligenceClient()
        _appModel = StateObject(wrappedValue: AppModel(modelContext: modelContainer.mainContext, client: client))
        URLCache.shared = URLCache(memoryCapacity: 64 * 1024 * 1024, diskCapacity: 256 * 1024 * 1024)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appModel)
                .tint(.orange)
        }
        .modelContainer(modelContainer)
    }
}
