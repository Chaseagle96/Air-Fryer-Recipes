import Foundation
import SwiftData

private enum JSONStorage {
    static func encode<T: Encodable>(_ value: T) -> String {
        guard let data = try? JSONEncoder().encode(value), let text = String(data: data, encoding: .utf8) else { return "[]" }
        return text
    }

    static func decode<T: Decodable>(_ type: T.Type, from text: String, fallback: T) -> T {
        guard let data = text.data(using: .utf8), let value = try? JSONDecoder().decode(type, from: data) else { return fallback }
        return value
    }
}

@Model
final class RecipeCacheRecord {
    @Attribute(.unique) var cacheKey: String
    var recipeID: String
    var verticalID: String
    var payloadJSON: String
    var cachedAt: Date

    init(recipe: RemoteRecipe) {
        cacheKey = "\(recipe.verticalID)|\(recipe.recipeID)"
        recipeID = recipe.recipeID
        verticalID = recipe.verticalID
        payloadJSON = JSONStorage.encode(recipe)
        cachedAt = .now
    }

    var recipe: RemoteRecipe? {
        guard let data = payloadJSON.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(RemoteRecipe.self, from: data)
    }
}

@Model
final class UserProfileRecord {
    @Attribute(.unique) var id: UUID
    var displayName: String
    var createdAt: Date

    init(id: UUID = UUID(), displayName: String) {
        self.id = id
        self.displayName = displayName
        createdAt = .now
    }
}

@Model
final class HouseholdRecord {
    @Attribute(.unique) var id: UUID
    var name: String
    var memberIDsJSON: String
    var adventureLevel: Int
    var hardVetoIngredientsJSON: String
    var createdAt: Date

    init(id: UUID = UUID(), name: String = "Household", memberIDs: [UUID] = []) {
        self.id = id
        self.name = name
        memberIDsJSON = JSONStorage.encode(memberIDs.map(\.uuidString))
        adventureLevel = 1
        hardVetoIngredientsJSON = "[]"
        createdAt = .now
    }

    var memberIDs: [UUID] {
        get { JSONStorage.decode([String].self, from: memberIDsJSON, fallback: []).compactMap(UUID.init(uuidString:)) }
        set { memberIDsJSON = JSONStorage.encode(newValue.map(\.uuidString)) }
    }
}

@Model
final class SavedRecipeRecord {
    @Attribute(.unique) var key: String
    var recipeID: String
    var profileID: UUID
    var verticalID: String
    var verticalName: String
    var title: String
    var source: String
    var sourceURLString: String
    var imageURLString: String
    var author: String
    var categoriesJSON: String
    var ingredientsJSON: String
    var rank: Int
    var rating: Double
    var ratingCount: Int
    var evidenceConfidence: Double
    var rankConfidence: Double
    var statusRaw: String
    var savedAt: Date

    init(recipe: RemoteRecipe, profileID: UUID, status: SavedRecipeStatus = .wantToTry) {
        key = "\(profileID.uuidString)|\(recipe.verticalID)|\(recipe.recipeID)"
        recipeID = recipe.recipeID
        self.profileID = profileID
        verticalID = recipe.verticalID
        verticalName = recipe.verticalName
        title = recipe.title
        source = recipe.source
        sourceURLString = recipe.canonicalURL.isEmpty ? recipe.url : recipe.canonicalURL
        imageURLString = recipe.imageURL
        author = recipe.author
        categoriesJSON = JSONStorage.encode(recipe.categories)
        ingredientsJSON = JSONStorage.encode(recipe.ingredients)
        rank = recipe.rank
        rating = recipe.rating
        ratingCount = recipe.ratingCount
        evidenceConfidence = recipe.evidenceConfidence
        rankConfidence = recipe.rankConfidence
        statusRaw = status.rawValue
        savedAt = .now
    }

    var status: SavedRecipeStatus {
        get { SavedRecipeStatus(rawValue: statusRaw) ?? .wantToTry }
        set { statusRaw = newValue.rawValue }
    }

    var categories: [String] { JSONStorage.decode([String].self, from: categoriesJSON, fallback: []) }
    var ingredients: [String] { JSONStorage.decode([String].self, from: ingredientsJSON, fallback: []) }
    var sourceURL: URL? { URL(string: sourceURLString) }
    var imageURL: URL? { imageURLString.isEmpty ? nil : URL(string: imageURLString) }

    func updateRemoteMetadata(from recipe: RemoteRecipe) {
        guard recipeID == recipe.recipeID, verticalID == recipe.verticalID else { return }
        verticalName = recipe.verticalName
        title = recipe.title
        source = recipe.source
        sourceURLString = recipe.canonicalURL.isEmpty ? recipe.url : recipe.canonicalURL
        imageURLString = recipe.imageURL
        author = recipe.author
        categoriesJSON = JSONStorage.encode(recipe.categories)
        ingredientsJSON = JSONStorage.encode(recipe.ingredients)
        rank = recipe.rank
        rating = recipe.rating
        ratingCount = recipe.ratingCount
        evidenceConfidence = recipe.evidenceConfidence
        rankConfidence = recipe.rankConfidence
    }
}

@Model
final class BehaviorEventRecord {
    @Attribute(.unique) var id: UUID
    var profileID: UUID
    var recipeID: String
    var verticalID: String
    var eventTypeRaw: String
    var timestamp: Date
    var contextJSON: String
    var isUndone: Bool

    init(
        id: UUID = UUID(),
        profileID: UUID,
        recipeID: String,
        verticalID: String,
        eventType: BehaviorEventType,
        context: [String: String] = [:]
    ) {
        self.id = id
        self.profileID = profileID
        self.recipeID = recipeID
        self.verticalID = verticalID
        eventTypeRaw = eventType.rawValue
        timestamp = .now
        contextJSON = JSONStorage.encode(context)
        isUndone = false
    }

    var eventType: BehaviorEventType? { BehaviorEventType(rawValue: eventTypeRaw) }
}

@Model
final class PersonalNoteRecord {
    @Attribute(.unique) var id: UUID
    var profileID: UUID
    var recipeID: String
    var text: String
    var createdAt: Date

    init(profileID: UUID, recipeID: String, text: String) {
        id = UUID()
        self.profileID = profileID
        self.recipeID = recipeID
        self.text = text
        createdAt = .now
    }
}

@Model
final class PersonalReviewRecord {
    @Attribute(.unique) var id: UUID
    var profileID: UUID
    var recipeID: String
    var overall: Int
    var taste: Int
    var ease: Int
    var value: Int
    var wouldMakeAgainRaw: String
    var householdReaction: String
    var notes: String
    var createdAt: Date

    init(
        profileID: UUID,
        recipeID: String,
        overall: Int,
        taste: Int,
        ease: Int,
        value: Int,
        wouldMakeAgain: WouldMakeAgain,
        householdReaction: String,
        notes: String
    ) {
        id = UUID()
        self.profileID = profileID
        self.recipeID = recipeID
        self.overall = overall
        self.taste = taste
        self.ease = ease
        self.value = value
        wouldMakeAgainRaw = wouldMakeAgain.rawValue
        self.householdReaction = householdReaction
        self.notes = notes
        createdAt = .now
    }

    var wouldMakeAgain: WouldMakeAgain { WouldMakeAgain(rawValue: wouldMakeAgainRaw) ?? .maybe }
}

@Model
final class CookingEventRecord {
    @Attribute(.unique) var id: UUID
    var profileID: UUID
    var recipeID: String
    var cookedAt: Date

    init(profileID: UUID, recipeID: String) {
        id = UUID()
        self.profileID = profileID
        self.recipeID = recipeID
        cookedAt = .now
    }
}

@Model
final class MealPlanEntry {
    @Attribute(.unique) var id: UUID
    var profileID: UUID
    var recipeID: String
    var verticalID: String
    var title: String
    var date: Date
    var servings: Int
    var status: String

    init(profileID: UUID, saved: SavedRecipeRecord, date: Date, servings: Int = 1) {
        id = UUID()
        self.profileID = profileID
        recipeID = saved.recipeID
        verticalID = saved.verticalID
        title = saved.title
        self.date = date
        self.servings = servings
        status = "planned"
    }
}

@Model
final class ShoppingListItem {
    @Attribute(.unique) var id: UUID
    var profileID: UUID
    var normalizedKey: String
    var displayName: String
    var amount: Double?
    var unit: String
    var originalLine: String
    var category: String
    var sourceRecipeIDsJSON: String
    var isChecked: Bool
    var isManual: Bool
    var createdAt: Date

    init(profileID: UUID, draft: ShoppingDraft, isManual: Bool = false) {
        id = UUID()
        self.profileID = profileID
        normalizedKey = draft.normalizedKey
        displayName = draft.displayName
        amount = draft.amount
        unit = draft.unit
        originalLine = draft.originalLine
        category = draft.category
        sourceRecipeIDsJSON = JSONStorage.encode(draft.sourceRecipeIDs)
        isChecked = false
        self.isManual = isManual
        createdAt = .now
    }

    var sourceRecipeIDs: [String] { JSONStorage.decode([String].self, from: sourceRecipeIDsJSON, fallback: []) }
}
