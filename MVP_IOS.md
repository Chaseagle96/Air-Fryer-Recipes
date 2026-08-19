# Recipe Intelligence iOS MVP

The iOS MVP turns Recipe Intelligence from a global ranking engine into the foundation of a private personal food-discovery system.

## Product loop

1. Choose a Recipe Intelligence vertical.
2. Swipe through ranked recipes.
3. Save, Skip, or choose Not Now.
4. Revisit saved recipes and use Help Me Pick to eliminate decision fatigue.
5. Put recipes on the coming week's plan.
6. Generate a combined shopping list from factual ingredient data.
7. Mark recipes cooked and record multidimensional reviews and notes.
8. Preserve every meaningful interaction as local, profile-scoped recommendation evidence.

## North-star separation

The architecture treats these as distinct questions:

- **Global quality:** What is a strong recipe? Recipe Intelligence answers this.
- **Personal fit:** What will this particular profile enjoy? The iOS event/persistence and recommendation interfaces begin this layer.
- **Household convergence:** What will multiple different profiles genuinely enjoy together? A separate household-convergence contract exists so future work does not collapse this into a simple average.

See `ios/README.md` for the build, backend contract, persistence model, accessibility strategy and known MVP limitations.
