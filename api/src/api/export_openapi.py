"""Write the OpenAPI schema to contracts/openapi.json. The frontend generates its TypeScript types from it.

python -m api.export_openapi [path]      # run from the repository root
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from api.main import create_app
from api.settings import ApiSettings


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "contracts" / "openapi.json"
    if not target.parent.is_dir():
        raise SystemExit("Run from the repository root, or pass the output path.")
    schema = create_app(ApiSettings(environment="test", storage_root="/nonexistent")).openapi()
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
