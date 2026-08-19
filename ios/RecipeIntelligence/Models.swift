import Foundation

enum SavedRecipeStatus: String, CaseIterable, Codable, Identifiable {
    case wantToTry = "Want to Try"
    case planned = "Planned"
    case cooked = "Cooked"
    case favorite = "Favorite"
    case archived = "Archived"

    var id: String { rawValue }
}

enum RecipeDecision: String, Codable {
    case save
    case skip
    case notNow
}

enum WouldMakeAgain: String, CaseIterable, Codable, Identifiable {
    case definitely = "Definitely"
    case probably = "Probably"
    case maybe = "Maybe"
    case probablyNot = "Probably Not"
    case never = "Never"

    var id: String { rawValue }
}

enum BehaviorEventType: String, Codable {
    case recipeImpression = "recipe_impression"
    case recipeOpened = "recipe_opened"
    case swipeSave = "swipe_save"
    case swipeSkip = "swipe_skip"
    case swipeNotNow = "swipe_not_now"
    case undoSwipe = "undo_swipe"
    case recipeSaved = "recipe_saved"
    case recipeUnsaved = "recipe_unsaved"
    case recipePlanned = "recipe_planned"
    case recipeUnplanned = "recipe_unplanned"
    case recipeCooked = "recipe_cooked"
    case recipeCookedAgain = "recipe_cooked_again"
    case recipeFavorited = "recipe_favorited"
    case personalReviewSubmitted = "personal_review_submitted"
    case noteAdded = "note_added"
    case shoppingListAdded = "shopping_list_added"
    case eliminationSelected = "elimination_selected"
    case eliminationRejected = "elimination_rejected"
    case originalSourceOpened = "original_source_opened"
}

struct VerticalCatalog: Codable {
    let schemaVersion: Int
    let verticals: [RecipeVertical]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case verticals
    }
}

struct RecipeVertical: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let icon: String
    let available: Bool
    let manifestURL: URL

    enum CodingKeys: String, CodingKey {
        case id, name, icon, available
        case manifestURL = "manifest_url"
    }

    static let fallbacks: [RecipeVertical] = [
        RecipeVertical(
            id: "air_fryer",
            name: "Air Fryer",
            icon: "wind",
            available: true,
            manifestURL: URL(string: "https://raw.githubusercontent.com/Chaseagle96/Recipe-Intelligence/main/docs/api/manifest.json")!
        ),
        RecipeVertical(
            id: "slow_cooker",
            name: "Slow Cooker",
            icon: "clock.arrow.circlepath",
            available: true,
            manifestURL: URL(string: "https://raw.githubusercontent.com/Chaseagle96/Recipe-Intelligence/main/verticals/slow_cooker/docs/api/manifest.json")!
        )
    ]
}

struct FeedManifest: Codable {
    let schemaVersion: Int
    let generatedAt: String
    let vertical: FeedVerticalDescriptor
    let recipeCount: Int
    let pageSize: Int
    let pages: [FeedPageReference]

    // Added additively to schema v1. Older feeds omit these fields, so the app
    // falls back to the ranked feed until that vertical publishes its corpus.
    var rankedRecipeCount: Int? = nil
    var corpusRecipeCount: Int? = nil
    var corpusPages: [FeedPageReference]? = nil
    var corpusStatusCounts: [String: Int]? = nil
    var catalogURLCount: Int? = nil

    var effectiveRankedRecipeCount: Int { rankedRecipeCount ?? recipeCount }
    var effectiveCorpusRecipeCount: Int { corpusRecipeCount ?? recipeCount }
    var effectiveCorpusPages: [FeedPageReference] { corpusPages ?? pages }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case generatedAt = "generated_at"
        case vertical
        case recipeCount = "recipe_count"
        case pageSize = "page_size"
        case pages
        case rankedRecipeCount = "ranked_recipe_count"
        case corpusRecipeCount = "corpus_recipe_count"
        case corpusPages = "corpus_pages"
        case corpusStatusCounts = "corpus_status_counts"
        case catalogURLCount = "catalog_url_count"
    }
}

struct FeedVerticalDescriptor: Codable {
    let id: String
    let name: String
    let sourceCount: Int

    enum CodingKeys: String, CodingKey {
        case id, name
        case sourceCount = "source_count"
    }
}

struct FeedPageReference: Codable, Hashable {
    let index: Int
    let path: String
    let count: Int
}

struct RecipePageEnvelope: Codable {
    let schemaVersion: Int
    let generatedAt: String
    let verticalID: String
    let verticalName: String
    let page: Int
    let recipes: [RemoteRecipe]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case generatedAt = "generated_at"
        case verticalID = "vertical_id"
        case verticalName = "vertical_name"
        case page, recipes
    }
}

struct RemoteRecipe: Codable, Identifiable, Hashable {
    let recipeID: String
    let verticalID: String
    let verticalName: String
    let title: String
    let source: String
    let combinedSources: String
    let url: String
    let canonicalURL: String
    let imageURL: String
    let author: String
    let categories: [String]
    let ingredients: [String]
    let hasInstructions: Bool
    let instructionCount: Int
    let rank: Int
    let rating: Double
    let ratingCount: Int
    let hierarchicalScore: Double
    let evidenceConfidence: Double
    let evidenceGrade: String
    let evidenceStatus: String
    let rankConfidence: Double
    let rankRangeLow: Int?
    let rankRangeHigh: Int?
    let rankProvenance: String

    // Full-corpus metadata. These remain optional so existing schema-v1 ranked
    // pages continue to decode while verticals roll out the richer publication.
    var isRanked: Bool? = nil
    var discoverEligible: Bool? = nil
    var exploreEligible: Bool? = nil
    var serveability: String? = nil
    var statusReasons: [String]? = nil
    var lastSeenAt: String? = nil
    var duplicateGroupID: String? = nil
    var duplicateConfidence: Double? = nil
    var duplicateRepresentativeRecipeID: String? = nil

    var id: String { recipeID }
    var sourceURL: URL? { URL(string: canonicalURL.isEmpty ? url : canonicalURL) }
    var photoURL: URL? { imageURL.isEmpty ? nil : URL(string: imageURL) }
    var isGloballyRanked: Bool { isRanked ?? rank > 0 }
    var isDiscoverEligible: Bool { discoverEligible ?? isGloballyRanked }
    var isExploreEligible: Bool { exploreEligible ?? isDiscoverEligible }

    var confidenceLabel: String {
        switch evidenceConfidence {
        case 0.9...: return "High-confidence rating"
        case 0.7..<0.9: return "Good rating evidence"
        default: return "Limited rating evidence"
        }
    }

    var rankingLabel: String {
        isGloballyRanked ? "#\(rank) \(verticalName)" : "Exploratory · \(verticalName)"
    }

    enum CodingKeys: String, CodingKey {
        case recipeID = "recipe_id"
        case verticalID = "vertical_id"
        case verticalName = "vertical_name"
        case title, source
        case combinedSources = "combined_sources"
        case url
        case canonicalURL = "canonical_url"
        case imageURL = "image_url"
        case author, categories, ingredients
        case hasInstructions = "has_instructions"
        case instructionCount = "instruction_count"
        case rank, rating
        case ratingCount = "rating_count"
        case hierarchicalScore = "hierarchical_score"
        case evidenceConfidence = "evidence_confidence"
        case evidenceGrade = "evidence_grade"
        case evidenceStatus = "evidence_status"
        case rankConfidence = "rank_confidence"
        case rankRangeLow = "rank_range_low"
        case rankRangeHigh = "rank_range_high"
        case rankProvenance = "rank_provenance"
        case isRanked = "is_ranked"
        case discoverEligible = "discover_eligible"
        case exploreEligible = "explore_eligible"
        case serveability
        case statusReasons = "status_reasons"
        case lastSeenAt = "last_seen_at"
        case duplicateGroupID = "duplicate_group_id"
        case duplicateConfidence = "duplicate_confidence"
        case duplicateRepresentativeRecipeID = "duplicate_representative_recipe_id"
    }
}

struct RecommendationSignals {
    let savedRecipeIDs: Set<String>
    let skippedRecipeIDs: Set<String>
    let notNowRecipeIDs: Set<String>
}

struct HouseholdMatch: Identifiable, Hashable {
    let recipe: RemoteRecipe
    let perProfileConfidence: [UUID: Double]
    let householdConfidence: Double
    var id: String { recipe.recipeID }
}
