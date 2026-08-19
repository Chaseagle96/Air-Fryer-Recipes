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
                Text("Choose from recipes you saved. The planner is intentionally lightweight in the MVP; intelligent weekly balancing comes next.")
                    .foregroundStyle(.secondary)
            }
            ForEach(dates, id: \.self) { date in
                Section(date.formatted(.dateTime.weekday(.wide).month().day())) {
                    let entries = entries(on: date)
                    if entries.isEmpty {
                        Button("Choose a recipe", systemImage: "plus") { selectedDate = date }
                    } else {
                        ForEach(entries) { entry in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(entry.title).font(.headline)
                                    Text(entry.verticalID.replacingOccurrences(of: "_", with: " ").capitalized)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button("Remove", systemImage: "trash", role: .destructive) { appModel.unplan(entry) }
                                    .labelStyle(.iconOnly)
                            }
                        }
                        Button("Replace", systemImage: "arrow.triangle.2.circlepath") { selectedDate = date }
                    }
                }
            }
        }
        .navigationTitle("This Week")
        .sheet(item: Binding(
            get: { selectedDate.map(DaySelection.init) },
            set: { selectedDate = $0?.date }
        )) { selection in
            NavigationStack { PlanRecipePicker(date: selection.date) }
        }
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
                    HStack {
                        RemoteRecipeImage(url: saved.imageURL, title: saved.title)
                            .frame(width: 64, height: 54)
                            .clipped()
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                        VStack(alignment: .leading) {
                            Text(saved.title).font(.headline)
                            Text(saved.verticalName).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .navigationTitle("Choose Recipe")
    }
}
