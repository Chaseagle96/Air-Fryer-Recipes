import SwiftData
import SwiftUI

struct ShoppingView: View {
    @EnvironmentObject private var appModel: AppModel
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \ShoppingListItem.createdAt) private var allItems: [ShoppingListItem]
    @State private var manualItem = ""

    private var items: [ShoppingListItem] { allItems.filter { $0.profileID == appModel.activeProfileID } }
    private var categories: [String] { Array(Set(items.map(\.category))).sorted() }

    var body: some View {
        List {
            Section {
                Button("Build from This Week", systemImage: "wand.and.stars") { appModel.generateShoppingList() }
                    .buttonStyle(.borderedProminent)
                HStack {
                    TextField("Add an item", text: $manualItem)
                        .textInputAutocapitalization(.sentences)
                    Button("Add") {
                        appModel.addManualShoppingItem(manualItem)
                        manualItem = ""
                    }
                }
            }

            ForEach(categories, id: \.self) { category in
                Section(category) {
                    ForEach(items.filter { $0.category == category }) { item in
                        Toggle(isOn: Binding(
                            get: { item.isChecked },
                            set: {
                                item.isChecked = $0
                                try? modelContext.save()
                            }
                        )) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(displayText(item))
                                if item.sourceRecipeIDs.count > 1 {
                                    Text("Used by \(item.sourceRecipeIDs.count) planned recipes")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        .swipeActions {
                            Button("Delete", role: .destructive) { appModel.deleteShoppingItem(item) }
                        }
                    }
                }
            }
        }
        .navigationTitle("Shopping")
        .overlay {
            if items.isEmpty {
                ContentUnavailableView("Your list is empty", systemImage: "cart", description: Text("Plan recipes, then build one combined ingredient list."))
                    .allowsHitTesting(false)
            }
        }
    }

    private func displayText(_ item: ShoppingListItem) -> String {
        guard let amount = item.amount else { return item.displayName }
        let amountText = amount.rounded() == amount ? String(Int(amount)) : String(format: "%.2f", amount).replacingOccurrences(of: ".00", with: "")
        return [amountText, item.unit, item.displayName].filter { !$0.isEmpty }.joined(separator: " ")
    }
}
