# TubeBendSheet Development Tasks
# Usage: make <target>

.PHONY: check lint typecheck test validate package clean-package

# Check Python syntax
check:
	@echo "Checking syntax..."
	@python3 -m py_compile $$(find . -name "*.py" -not -path "./typings/*")
	@echo "Syntax OK"

# Run linter
lint:
	@ruff check . --ignore E402,E501,E712,E722,F403,I001,UP037,W291,W292,W293 --exclude typings

# Run type checker
typecheck:
	@pipx run pyright --project pyrightconfig.json

# Run unit tests with pytest
test:
	@pytest tests/ -v --tb=short

# Run all validation (use before committing)
validate: check lint test
	@echo ""
	@echo "All validation passed!"

# Clean previous package
clean-package:
	@rm -f TubeBendSheet.zip

# Create distribution zip for App Store submission
package: clean-package
	@echo "Creating TubeBendSheet.zip..."
	@zip -r TubeBendSheet.zip . \
		-x ".*" \
		-x "*/.*" \
		-x "__pycache__/*" \
		-x "*/__pycache__/*" \
		-x "tests/*" \
		-x "typings/*" \
		-x "*.pyc" \
		-x "Makefile" \
		-x "pyproject.toml" \
		-x "pyrightconfig.json" \
		-x "CLAUDE.md" \
		-x "TubeBendSheet.zip"
	@echo "Created TubeBendSheet.zip"
	@unzip -l TubeBendSheet.zip | tail -1
