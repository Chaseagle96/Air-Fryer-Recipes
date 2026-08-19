import Foundation

enum SampleData {
    static let recipes: [RemoteRecipe] = [
        sample(id: "af-chicken", verticalID: "air_fryer", verticalName: "Air Fryer", title: "Crispy Air Fryer Chicken Thighs", source: "example.com", rank: 1, rating: 4.9, count: 3200, categories: ["Chicken"], ingredients: ["2 lb chicken thighs", "1 tablespoon olive oil", "1 teaspoon garlic powder"]),
        sample(id: "af-potatoes", verticalID: "air_fryer", verticalName: "Air Fryer", title: "Golden Air Fryer Potatoes", source: "example.com", rank: 2, rating: 4.8, count: 2100, categories: ["Potatoes"], ingredients: ["2 pounds potatoes", "1 tablespoon olive oil", "1 teaspoon salt"]),
        sample(id: "af-salmon", verticalID: "air_fryer", verticalName: "Air Fryer", title: "Air Fryer Garlic Salmon", source: "example.com", rank: 3, rating: 4.8, count: 1400, categories: ["Seafood"], ingredients: ["4 salmon fillets", "2 cloves garlic", "1 lemon"]),
        sample(id: "af-broccoli", verticalID: "air_fryer", verticalName: "Air Fryer", title: "Crispy Parmesan Broccoli", source: "example.com", rank: 4, rating: 4.7, count: 900, categories: ["Vegetables"], ingredients: ["1 pound broccoli", "1/2 cup parmesan cheese", "1 tablespoon olive oil"]),
        sample(id: "sc-ribs", verticalID: "slow_cooker", verticalName: "Slow Cooker", title: "Slow Cooker Baby Back Ribs", source: "example.com", rank: 1, rating: 4.8, count: 1377, categories: ["Pork"], ingredients: ["3 pounds baby back ribs", "1 cup barbecue sauce", "1 onion"]),
        sample(id: "sc-roast", verticalID: "slow_cooker", verticalName: "Slow Cooker", title: "Easy Slow Cooker Pot Roast", source: "example.com", rank: 2, rating: 4.7, count: 1968, categories: ["Beef"], ingredients: ["3 pounds beef roast", "2 onions", "4 carrots", "2 cups beef broth"]),
        sample(id: "sc-taco", verticalID: "slow_cooker", verticalName: "Slow Cooker", title: "Slow Cooker Taco Soup", source: "example.com", rank: 3, rating: 4.6, count: 2426, categories: ["Beef"], ingredients: ["1 pound ground beef", "1 onion", "2 cans black beans", "1 can tomatoes"]),
        sample(id: "sc-beans", verticalID: "slow_cooker", verticalName: "Slow Cooker", title: "Slow-Cooked Green Beans", source: "example.com", rank: 4, rating: 4.7, count: 318, categories: ["Vegetables"], ingredients: ["2 pounds green beans", "4 slices bacon", "1 onion"])
    ]

    private static func sample(
        id: String,
        verticalID: String,
        verticalName: String,
        title: String,
        source: String,
        rank: Int,
        rating: Double,
        count: Int,
        categories: [String],
        ingredients: [String]
    ) -> RemoteRecipe {
        RemoteRecipe(
            recipeID: id,
            verticalID: verticalID,
            verticalName: verticalName,
            title: title,
            source: source,
            combinedSources: source,
            url: "https://example.com/\(id)",
            canonicalURL: "https://example.com/\(id)",
            imageURL: "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=1200&q=80",
            author: "Recipe Intelligence Preview",
            categories: categories,
            ingredients: ingredients,
            hasInstructions: true,
            instructionCount: 6,
            rank: rank,
            rating: rating,
            ratingCount: count,
            hierarchicalScore: rating - 0.15,
            evidenceConfidence: 0.95,
            evidenceGrade: "A",
            evidenceStatus: "verified",
            rankConfidence: 0.9,
            rankRangeLow: rank,
            rankRangeHigh: rank + 2,
            rankProvenance: "Preview fixture"
        )
    }
}
