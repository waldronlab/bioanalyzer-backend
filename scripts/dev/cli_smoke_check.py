#!/usr/bin/env python3
"""
BioAnalyzer CLI Test - Simple test without dependencies
"""


def check_cli_structure():
    """Test that the CLI structure is correct."""
    print("🧪 Testing BioAnalyzer Package CLI Structure...")

    # Test CLI file exists
    import os

    cli_path = "scripts/cli.py"
    if os.path.exists(cli_path):
        print("✅ CLI file exists")
    else:
        print("❌ CLI file missing")
        return False

    # Test main.py exists
    main_path = "scripts/main.py"
    if os.path.exists(main_path):
        print("✅ Main.py file exists")
    else:
        print("❌ Main.py file missing")
        return False

    # Test app directory structure
    app_dirs = ["app", "app/api", "app/services", "app/models", "app/utils"]
    for dir_path in app_dirs:
        if os.path.exists(dir_path):
            print(f"✅ {dir_path} directory exists")
        else:
            print(f"❌ {dir_path} directory missing")
            return False

    # Test configuration files
    config_files = ["requirements.txt", "setup.py", "README.md"]
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"✅ {config_file} exists")
        else:
            print(f"❌ {config_file} missing")
            return False

    print("\n🎉 All structure tests passed!")
    return True


def show_field_info():
    """Test field information display."""
    print("\n📋 BugSigDB Essential Fields:")
    print("=" * 50)

    fields = {
        "host_species": {
            "name": "Host Species",
            "description": "The host organism being studied (e.g., Human, Mouse, Rat)",
            "required": True,
        },
        "body_site": {
            "name": "Body Site",
            "description": "Where the microbiome sample was collected (e.g., Gut, Oral, Skin)",
            "required": True,
        },
        "condition": {
            "name": "Condition",
            "description": "What disease, treatment, or exposure is being studied",
            "required": True,
        },
        "sequencing_type": {
            "name": "Sequencing Type",
            "description": "What molecular method was used (e.g., 16S, metagenomics)",
            "required": True,
        },
        "taxa_level": {
            "name": "Taxa Level",
            "description": "What taxonomic level was analyzed (e.g., phylum, genus, species)",
            "required": True,
        },
        "sample_size": {
            "name": "Sample Size",
            "description": "Number of samples or participants analyzed",
            "required": True,
        },
    }

    for field_key, field_info in fields.items():
        print(f"\n{field_info['name']} ({field_key}):")
        print(f"  Description: {field_info['description']}")
        print(f"  Required: {'Yes' if field_info['required'] else 'No'}")

    print("\n\nField Status Values:")
    print("-" * 30)
    status_values = {
        "PRESENT": "Information is complete and clear",
        "PARTIALLY_PRESENT": "Some information available but incomplete",
        "ABSENT": "Information is missing",
    }

    for status, description in status_values.items():
        print(f"  {status}: {description}")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    print("🚀 BioAnalyzer Package CLI Test")
    print("=" * 40)

    # Check structure
    if check_cli_structure():
        # Show field info
        show_field_info()

        print("\n✅ Package CLI structure is correct!")
        print("📝 To use the CLI, install dependencies:")
        print("   pip install -r requirements.txt")
        print("   python3 scripts/cli.py fields")
        print("   python3 scripts/cli.py analyze 12345678")
    else:
        print("\n❌ Package CLI structure has issues!")
