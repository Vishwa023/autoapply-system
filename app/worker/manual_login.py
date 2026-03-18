from __future__ import annotations

from app.runtime_profile import load_runtime_profile
from app.services.instahyre_source import crawl_instahyre_opportunities


def main() -> None:
    print("Opening Instahyre login flow in a browser window...", flush=True)
    result = crawl_instahyre_opportunities(profile=load_runtime_profile(), manual_login=True)
    print(result.details, flush=True)


if __name__ == "__main__":
    main()
