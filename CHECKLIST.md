# RTHYM-MOC Open Source Best Practices Checklist

This checklist will help you systematically improve the quality, reliability, and community readiness of your library.

## Testing
- [x] All features/scenarios have automated tests
	Coverage tracked in `docs/test_coverage_matrix.md`
- [x] Edge cases and invalid input are tested
- [ ] Parametrized tests for input variations
- [ ] Regression tests with reference outputs
- [ ] All assertions have clear, descriptive messages
- [ ] Numerical tolerances are explicit and documented
- [ ] Tests are isolated (no shared state)
- [ ] Random seeds set for reproducibility (if needed)

## Continuous Integration (CI)
- [ ] GitHub Actions (or similar) runs tests on all pushes/PRs
- [ ] CI covers all supported OSes and Python versions
- [ ] Test coverage is measured (pytest-cov)
- [ ] Coverage is uploaded to Codecov/Coveralls
- [ ] CI runs linting and type checks

## Linting & Type Checking
- [ ] Code style enforced (black, flake8, or ruff)
- [ ] All functions have type hints
- [ ] mypy or similar runs in CI
- [ ] Pre-commit hooks for style and linting

## Documentation
- [ ] All public functions/classes have docstrings
- [ ] Each test has a docstring explaining its purpose
- [ ] Example scripts and notebooks are provided
- [ ] Reference data (CSV/JSON) is versioned and documented
- [ ] README includes usage, install, and test instructions
- [ ] Badges for build, coverage, PyPI, etc.
- [ ] CONTRIBUTING.md with test/contribution instructions

## Community & Maintenance
- [ ] GitHub Issues/Projects used to track progress
- [ ] Regular review/refactor schedule
- [ ] Encourage and document community contributions
- [ ] Use pytest skip/xfail for optional/known issues

---

**How to use:**
- Work through one section at a time
- Check off items as you complete them
- Review regularly and update as needed
