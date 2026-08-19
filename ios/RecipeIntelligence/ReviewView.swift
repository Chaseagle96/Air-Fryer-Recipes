import SwiftUI

struct ReviewFormView: View {
    @EnvironmentObject private var appModel: AppModel
    @Environment(\.dismiss) private var dismiss
    let saved: SavedRecipeRecord
    @State private var overall = 4
    @State private var taste = 4
    @State private var ease = 4
    @State private var value = 4
    @State private var wouldMakeAgain: WouldMakeAgain = .probably
    @State private var householdReaction = ""
    @State private var notes = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Your experience") {
                    ratingStepper("Overall", value: $overall)
                    ratingStepper("Taste", value: $taste)
                    ratingStepper("Ease", value: $ease)
                    ratingStepper("Value", value: $value)
                }
                Section("Would you make it again?") {
                    Picker("Make again", selection: $wouldMakeAgain) {
                        ForEach(WouldMakeAgain.allCases) { Text($0.rawValue).tag($0) }
                    }
                }
                Section("Household") {
                    TextField("How did everyone react?", text: $householdReaction, axis: .vertical)
                }
                Section("Notes") {
                    TextField("What should you remember next time?", text: $notes, axis: .vertical)
                        .lineLimit(3...7)
                }
            }
            .navigationTitle("Review Recipe")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        appModel.submitReview(
                            for: saved,
                            overall: overall,
                            taste: taste,
                            ease: ease,
                            value: value,
                            wouldMakeAgain: wouldMakeAgain,
                            householdReaction: householdReaction,
                            notes: notes
                        )
                        dismiss()
                    }
                    .accessibilityIdentifier("review.save")
                }
            }
        }
    }

    private func ratingStepper(_ title: String, value: Binding<Int>) -> some View {
        Stepper(value: value, in: 1...5) {
            HStack {
                Text(title)
                Spacer()
                Text("\(value.wrappedValue) / 5").fontWeight(.semibold)
            }
        }
        .accessibilityLabel("\(title) rating, \(value.wrappedValue) out of 5")
    }
}
