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
}
