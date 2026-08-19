import SwiftData
import SwiftUI

struct PlannerView: View {
    @EnvironmentObject private var appModel: AppModel
    @Query(sort: \MealPlanEntry.date) private var allEntries: [MealPlanEntry]
    @State private var selectedDate: Date?

    private var dates: [Date] {
        let start = Calendar.current.startOfDay(for: .now)
        return (0..<7).compactMap { Calendar.current.date(byAdding: .day, value: $0, to: start) }
    }

    var body: some View {
        List {
            Section {
                Label("Plan from recipes you already trust", systemImage: "calendar.badge.checkmark")
                    .font(.headline)
                Text("Choose from saved recipes now. Recipe Intelligence can layer smarter weekly balancing on top without changing this simple planning flow.")
                    .foregroundStyle(.secondary)
            }
            ForEach(dates, id: \.self) { date in
                Section(date.formatted(.dateTime.weekday(.wide).month().day())) {
                    let entries = entries(on: date)
                    if entries.isEmpty {
                        Button("Choose a recipe", systemImage: "plus") { selectedDate = date }
                    } else {
                        ForEach(entries) { entry in
                            HStack(spacing: 12) {
                                Image(systemName: "fork.knife.circle.fill")
                                    .font(.title2)
                                    .foregroundStyle(RecipeDesign.accent)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(entry.title).font(.headline)
                                    Text(entry.verticalID.replacingOccurrences(of: "_", with: " ").capitalized)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button("Remove", systemImage: "trash", role: .destructive) { appModel.unplan(entry) }
                                    .labelStyle(.iconOnly)
                            }
                            .padding(.vertical, 2)
                        }
                        Button("Replace", systemImage: "arrow.triangle.2.circlepath") { selectedDate = date }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .recipeScreenBackground()
        .navigationTitle("This Week")
        .sheet(item: Binding(
            get: { selectedDate.map(DaySelection.init) },
            set: { selectedDate = $0?.date }
        )) { selection in
            NavigationStack { PlanRecipePicker(date: selection.date) }
        }
        .recipeToolbarBehavior()
    }

    private func entries(on date: Date) -> [MealPlanEntry] {
        allEntries.filter { $0.profileID == appModel.activeProfileID && Calendar.current.isDate($0.date, inSameDayAs: date) }
    }
}

private struct DaySelection: Identifiable {
    let date: Date
    var id: Date { date }
}

private struct PlanRecipePicker: View {
    @EnvironmentObject private var appModel: AppModel
    @Environment(\.dismiss) private var dismiss
    @Query(sort: \SavedRecipeRecord.savedAt, order: .reverse) private var allSaved: [SavedRecipeRecord]
    let date: Date

    var body: some View {
        List {
            ForEach(allSaved.filter { $0.profileID == appModel.activeProfileID && $0.status != .archived }) { saved in
                Button {
                    appModel.planRecipe(saved, on: date)
                    dismiss()
                } label: {
                    HStack(spacing: 12) {
                        RemoteRecipeImage(url: saved.imageURL, title: saved.title)
                            .frame(width: 66, height: 56)
                            .clipped()
                            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        VStack(alignment: .leading, spacing: 3) {
                            Text(saved.title).font(.headline)
                            Text(saved.verticalName).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 2)
                }
                .buttonStyle(.plain)
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .recipeScreenBackground()
        .navigationTitle("Choose Recipe")
        .recipeToolbarBehavior()
    }
}
