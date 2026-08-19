import Foundation

struct ShoppingDraft: Hashable {
    var normalizedKey: String
    var displayName: String
    var amount: Double?
    var unit: String
    var originalLine: String
    var category: String
    var sourceRecipeIDs: [String]
}

struct IngredientParser {
    private static let units: [String: String] = [
        "cup": "cup", "cups": "cup", "c": "cup",
        "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp",
        "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp",
        "ounce": "oz", "ounces": "oz", "oz": "oz",
        "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
        "gram": "g", "grams": "g", "g": "g",
        "kilogram": "kg", "kilograms": "kg", "kg": "kg",
        "milliliter": "ml", "milliliters": "ml", "ml": "ml",
        "liter": "l", "liters": "l", "l": "l"
    ]

    static func parse(_ line: String, recipeID: String) -> ShoppingDraft {
        var tokens = line.trimmingCharacters(in: .whitespacesAndNewlines).split(separator: " ").map(String.init)
        let original = line.trimmingCharacters(in: .whitespacesAndNewlines)
        var amount: Double?
        if let first = tokens.first, let value = number(first) {
            amount = value
            tokens.removeFirst()
            if let next = tokens.first, next.contains("/"), let fraction = number(next) {
                amount = value + fraction
                tokens.removeFirst()
            }
        }

        var unit = ""
        if let first = tokens.first {
            let cleaned = first.lowercased().trimmingCharacters(in: .punctuationCharacters)
            if let canonical = units[cleaned] {
                unit = canonical
                tokens.removeFirst()
            }
        }

        if tokens.first?.lowercased() == "of" { tokens.removeFirst() }
        let name = tokens.joined(separator: " ").trimmingCharacters(in: CharacterSet(charactersIn: ",.;"))
        let display = name.isEmpty ? original : name
        let normalizedName = normalizeName(display)
        let key = "\(normalizedName)|\(unit)"
        return ShoppingDraft(
            normalizedKey: key,
            displayName: display,
            amount: amount,
            unit: unit,
            originalLine: original,
            category: category(for: normalizedName),
            sourceRecipeIDs: [recipeID]
        )
    }

    private static func number(_ token: String) -> Double? {
        let cleaned = token.trimmingCharacters(in: CharacterSet(charactersIn: ","))
        if let direct = Double(cleaned) { return direct }
        let parts = cleaned.split(separator: "/")
        guard parts.count == 2, let numerator = Double(parts[0]), let denominator = Double(parts[1]), denominator != 0 else { return nil }
        return numerator / denominator
    }

    private static func normalizeName(_ value: String) -> String {
        value.lowercased()
            .replacingOccurrences(of: "(", with: " ")
            .replacingOccurrences(of: ")", with: " ")
            .replacingOccurrences(of: ",", with: " ")
            .split(separator: " ")
            .map(String.init)
            .joined(separator: " ")
    }

    private static func category(for name: String) -> String {
        let produce = ["onion", "garlic", "pepper", "potato", "carrot", "celery", "tomato", "cilantro", "parsley", "lemon", "lime", "apple", "broccoli", "spinach"]
        let meat = ["chicken", "beef", "pork", "turkey", "sausage", "salmon", "shrimp", "fish"]
        let dairy = ["milk", "cream", "cheese", "butter", "yogurt", "sour cream", "egg"]
        let frozen = ["frozen"]
        let bakery = ["bread", "bun", "tortilla", "roll"]
        if produce.contains(where: name.contains) { return "Produce" }
        if meat.contains(where: name.contains) { return "Meat / Seafood" }
        if dairy.contains(where: name.contains) { return "Dairy" }
        if frozen.contains(where: name.contains) { return "Frozen" }
        if bakery.contains(where: name.contains) { return "Bakery" }
        return "Pantry / Other"
    }
}

struct ShoppingListService {
    func combine(savedRecipes: [SavedRecipeRecord]) -> [ShoppingDraft] {
        var merged: [String: ShoppingDraft] = [:]
        var unmergeable: [ShoppingDraft] = []

        for saved in savedRecipes {
            for ingredient in saved.ingredients {
                let parsed = IngredientParser.parse(ingredient, recipeID: saved.recipeID)
                guard parsed.amount != nil else {
                    unmergeable.append(parsed)
                    continue
                }
                if var existing = merged[parsed.normalizedKey], existing.unit == parsed.unit, let lhs = existing.amount, let rhs = parsed.amount {
                    existing.amount = lhs + rhs
                    existing.sourceRecipeIDs = Array(Set(existing.sourceRecipeIDs + parsed.sourceRecipeIDs)).sorted()
                    merged[parsed.normalizedKey] = existing
                } else {
                    merged[parsed.normalizedKey] = parsed
                }
            }
        }

        return (Array(merged.values) + unmergeable).sorted {
            if $0.category == $1.category { return $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending }
            return $0.category < $1.category
        }
    }
}
