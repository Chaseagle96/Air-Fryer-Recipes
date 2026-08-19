import SwiftData
import SwiftUI

struct ProfileView: View {
    @EnvironmentObject private var appModel: AppModel
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \UserProfileRecord.createdAt) private var profiles: [UserProfileRecord]
    @Query private var households: [HouseholdRecord]
    @Query(sort: \BehaviorEventRecord.timestamp, order: .reverse) private var events: [BehaviorEventRecord]
    @State private var newProfileName = ""

    var body: some View {
        Form {
            Section("Active taste profile") {
                if !profiles.isEmpty {
                    Picker("Profile", selection: Binding(
                        get: { appModel.activeProfileID ?? profiles[0].id },
                        set: { id in if let profile = profiles.first(where: { $0.id == id }) { appModel.setActiveProfile(profile) } }
                    )) {
                        ForEach(profiles) { profile in Text(profile.displayName).tag(profile.id) }
                    }
                }
                HStack {
                    TextField("Add another person", text: $newProfileName)
                    Button("Add") {
                        appModel.addProfile(named: newProfileName)
                        newProfileName = ""
                    }
                    .disabled(newProfileName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }

            if let household = households.first {
                Section("Household discovery") {
                    Stepper(value: Binding(
                        get: { household.adventureLevel },
                        set: {
                            household.adventureLevel = min(max($0, 0), 3)
                            try? modelContext.save()
                        }
                    ), in: 0...3) {
                        HStack(spacing: 12) {
                            Image(systemName: "safari.fill")
                                .font(.title2)
                                .foregroundStyle(RecipeDesign.accent)
                            VStack(alignment: .leading) {
                                Text("Adventure level")
                                Text(adventureLabel(household.adventureLevel))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    Text("Household profiles stay separate so future recommendations can find recipes where different tastes genuinely converge instead of merely averaging preferences.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            Section("Taste learning") {
                LabeledContent {
                    Text(events.filter { $0.profileID == appModel.activeProfileID && !$0.isUndone }.count.formatted())
                        .fontWeight(.semibold)
                } label: {
                    Label("Signals captured", systemImage: "waveform.path.ecg")
                }
                Text("Saves, skips, Not Now choices, cooking history, repeats, notes, reviews and planning actions stay on this device in the MVP. They form the training-quality event history for future personalization.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Section("Privacy") {
                Label("Personal taste data stays on this device", systemImage: "lock.shield.fill")
                    .foregroundStyle(.primary)
                Text("No third-party analytics SDK is included. Recipe Intelligence receives no private notes or personal reviews from this MVP.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .scrollContentBackground(.hidden)
        .recipeScreenBackground()
        .navigationTitle("Taste")
        .recipeToolbarBehavior()
    }

    private func adventureLabel(_ level: Int) -> String {
        switch level {
        case 0: return "Comfort — mostly familiar winners"
        case 1: return "Balanced — familiar plus some discovery"
        case 2: return "Adventurous — substantial exploration"
        default: return "Surprise me — maximum discovery"
        }
    }
}
