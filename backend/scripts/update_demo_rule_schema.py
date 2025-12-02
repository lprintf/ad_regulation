"""
Update existing demo_spend_guard rule with complete PARAMETERS_SCHEMA from script file.

Usage:
    python scripts/update_demo_rule_schema.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import init_db, close_db, RuleDefinitionDocument


async def main():
    await init_db()

    try:
        # Find the demo rule
        rule_name = "demo_spend_guard"
        doc = await RuleDefinitionDocument.find_one(
            RuleDefinitionDocument.name == rule_name
        )

        if not doc:
            print(f"❌ Rule '{rule_name}' not found in database")
            return

        print(f"✓ Found rule '{rule_name}' (id={doc.id})")
        print(f"  Current parameters_schema has {len(doc.parameters_schema)} keys")

        # Read the script file
        script_path = Path("rules/scripts/demo_spend_guard.py")
        if not script_path.exists():
            print(f"❌ Script file not found: {script_path}")
            return

        code = script_path.read_text(encoding="utf-8")

        # Extract PARAMETERS_SCHEMA
        namespace = {}
        exec(code, namespace)

        if "PARAMETERS_SCHEMA" not in namespace:
            print(f"❌ PARAMETERS_SCHEMA not found in script")
            return

        new_schema = namespace["PARAMETERS_SCHEMA"]
        print(f"✓ Extracted PARAMETERS_SCHEMA with {len(new_schema)} keys:")
        for key in new_schema.keys():
            print(f"    - {key}")

        # Update the document
        doc.parameters_schema = new_schema
        doc.code = code  # Also update code in case it changed
        await doc.save()

        print(f"✓ Updated rule '{rule_name}' successfully!")
        print(f"  New parameters_schema has {len(doc.parameters_schema)} keys")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
