#!/usr/bin/env python3
"""Refresh the FC26 transfer feed from public Transfermarkt club rosters.

The job is deliberately conservative:
- a roster must parse to a plausible size;
- failed teams keep their last known-good snapshot;
- a widespread fetch failure aborts without touching published data;
- only safe FC26 identities are emitted as automatic transfers.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from lxml import html as lxml_html


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://www.transfermarkt.com.tr"
DEFAULT_TEAMS = ROOT / "automation" / "data" / "teams.json"
DEFAULT_IDENTITIES = ROOT / "automation" / "data" / "fc_identities.json"
DEFAULT_STATE = ROOT / "automation" / "state" / "rosters.json"
DEFAULT_OUTPUT = ROOT / "docs" / "data.json"


def clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def norm(value: Any) -> str:
    text = clean(value).replace("İ", "I").replace("ı", "i")
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    ).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def as_numeric_text(value: Any) -> str | None:
    text = clean(value)
    if not text or not text.isdigit():
        return None
    return str(int(text))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def text_content(node: Any) -> str:
    return clean(" ".join(node.itertext()))


def parse_player_id(href: str) -> str | None:
    match = re.search(r"/profil/spieler/(\d+)", href or "")
    return str(int(match.group(1))) if match else None


def parse_roster_html(page: str) -> list[dict[str, str]]:
    """Parse the largest Transfermarkt roster table on a club page."""
    tree = lxml_html.fromstring(page)
    tables = tree.xpath(
        '//table[contains(concat(" ",normalize-space(@class)," "), " items ")]'
    )
    best: list[dict[str, str]] = []

    for table in tables:
        found: dict[str, dict[str, str]] = {}
        rows = table.xpath('./tbody/tr[.//a[contains(@href,"/profil/spieler/")]]')
        for row in rows:
            links = row.xpath('.//a[contains(@href,"/profil/spieler/")]')
            if not links:
                continue
            link = links[0]
            tm_id = parse_player_id(link.get("href") or "")
            if tm_id is None:
                continue
            name = clean(link.get("title") or text_content(link))
            if not name:
                continue
            found[tm_id] = {"tm_id": tm_id, "name": name}
        if len(found) > len(best):
            best = list(found.values())

    return sorted(best, key=lambda row: int(row["tm_id"]))


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
        }
    )
    return session


def roster_url(team: dict[str, Any]) -> str:
    return (
        f"{BASE_URL}/{team['slug']}/startseite/verein/{int(team['tm_id'])}"
    )


def fetch_roster(
    session: requests.Session,
    team: dict[str, Any],
    retries: int,
) -> tuple[str, list[dict[str, str]]]:
    url = roster_url(team)
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=35, allow_redirects=True)
            response.raise_for_status()
            body = response.text
            lowered = body.casefold()
            if len(body) < 1000 or any(
                marker in lowered
                for marker in ("captcha", "cf-chl-", "not a robot", "robot olmad")
            ):
                raise RuntimeError("bot doğrulama veya geçersiz kısa yanıt")
            players = parse_roster_html(body)
            if not 8 <= len(players) <= 80:
                raise RuntimeError(f"şüpheli kadro büyüklüğü: {len(players)}")
            return url, players
        except Exception as exc:  # network/parser boundary
            last_error = exc
            if attempt < retries:
                time.sleep(2.0 * attempt)

    raise RuntimeError(f"{team['fc_team_name']}: {last_error}")


def membership_index(state: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for team_id, team in state.get("teams", {}).items():
        for player in team.get("players", []):
            tm_id = as_numeric_text(player.get("tm_id"))
            if tm_id is None:
                continue
            result[tm_id].append(
                {
                    "fc_team_id": str(team_id),
                    "team_name": clean(team.get("fc_team_name")),
                    "player_name": clean(player.get("name")),
                }
            )
    return result


def site_identity_index(site: dict[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    priorities = {"creates": 0, "unresolved": 1, "exists": 2, "transfers": 3}
    selected_priority: dict[str, int] = {}

    for category in ("creates", "unresolved", "exists", "transfers"):
        for row in site.get(category, []):
            tm_id = as_numeric_text(row.get("tm_id"))
            if tm_id is None or priorities[category] < selected_priority.get(tm_id, -1):
                continue
            selected_priority[tm_id] = priorities[category]
            result[tm_id] = {
                "fc_id": as_numeric_text(row.get("fc_id")) or "",
                "player": clean(row.get("player")),
                "source": clean(row.get("source")),
                "target": clean(row.get("target")),
                "category": category,
            }
    return result


def unique_name_index(identities: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fc_id, player in identities.get("players", {}).items():
        item = dict(player)
        item["fc_id"] = str(fc_id)
        name_key = norm(item.get("name"))
        if name_key:
            candidates[name_key].append(item)
    return {key: rows[0] for key, rows in candidates.items() if len(rows) == 1}


def remove_tm_id(rows: list[dict[str, Any]], tm_id: str) -> list[dict[str, Any]]:
    return [row for row in rows if as_numeric_text(row.get("tm_id")) != tm_id]


def reconcile(
    site: dict[str, Any],
    identities: dict[str, Any],
    old_state: dict[str, Any],
    new_state: dict[str, Any],
) -> dict[str, int]:
    """Apply only roster membership changes to the published feed."""
    old_membership = membership_index(old_state)
    new_membership = membership_index(new_state)
    site_ids = site_identity_index(site)
    by_unique_name = unique_name_index(identities)
    fc_players = identities.get("players", {})

    transfers = list(site.get("transfers", []))
    creates = list(site.get("creates", []))
    added_transfers = 0
    updated_transfers = 0
    returned_to_base = 0
    review_items = 0

    changed_ids = sorted(
        {
            tm_id
            for tm_id in set(old_membership) | set(new_membership)
            if {row["fc_team_id"] for row in old_membership.get(tm_id, [])}
            != {row["fc_team_id"] for row in new_membership.get(tm_id, [])}
        },
        key=int,
    )

    for tm_id in changed_ids:
        destinations = new_membership.get(tm_id, [])
        if len(destinations) != 1:
            # Removed players and duplicated/loan membership need human review.
            continue

        destination = destinations[0]
        target_team_id = destination["fc_team_id"]
        target_name = destination["team_name"]
        player_name = destination["player_name"]
        previous = old_membership.get(tm_id, [])
        previous_name = previous[0]["team_name"] if len(previous) == 1 else ""

        known = site_ids.get(tm_id, {})
        fc_id = as_numeric_text(known.get("fc_id"))
        identity = fc_players.get(fc_id, {}) if fc_id else {}

        if not fc_id:
            identity = by_unique_name.get(norm(player_name), {})
            fc_id = as_numeric_text(identity.get("fc_id"))

        if fc_id:
            baseline_team_ids = {
                str(value) for value in identity.get("team_ids", [])
            }
            old_transfer = next(
                (
                    row
                    for row in transfers
                    if as_numeric_text(row.get("tm_id")) == tm_id
                ),
                None,
            )
            transfers = remove_tm_id(transfers, tm_id)
            creates = remove_tm_id(creates, tm_id)

            if target_team_id in baseline_team_ids:
                if old_transfer is not None:
                    returned_to_base += 1
                continue

            display_name = clean(identity.get("name")) or clean(known.get("player")) or player_name
            baseline_names = [clean(value) for value in identity.get("team_names", []) if clean(value)]
            source_name = (
                previous_name
                or clean(known.get("source"))
                or (baseline_names[0] if baseline_names else "-")
            )
            new_row = {
                "key": f"TRANSFER|{fc_id}|{tm_id}|{target_name}",
                "fc_id": fc_id,
                "tm_id": tm_id,
                "player": display_name,
                "source": source_name,
                "target": target_name,
                "reason": "DAILY_TRANSFERMARKT_ROSTER_CHANGE",
            }
            transfers.append(new_row)
            if old_transfer is None:
                added_transfers += 1
            elif clean(old_transfer.get("target")) != target_name:
                updated_transfers += 1
        else:
            creates = remove_tm_id(creates, tm_id)
            creates.append(
                {
                    "key": f"CREATE|-|{tm_id}|{target_name}|daily",
                    "fc_id": "-",
                    "tm_id": tm_id,
                    "player": player_name,
                    "source": previous_name or clean(known.get("source")) or "-",
                    "target": target_name,
                    "reason": "DAILY_CHANGE_NO_SAFE_FC26_IDENTITY",
                }
            )
            review_items += 1

    transfers.sort(key=lambda row: (norm(row.get("target")), norm(row.get("player")), clean(row.get("fc_id"))))
    creates.sort(key=lambda row: (norm(row.get("target")), norm(row.get("player")), clean(row.get("tm_id"))))
    site["transfers"] = transfers
    site["creates"] = creates
    summary = site.setdefault("summary", {})
    summary["transfers"] = len(transfers)
    summary["creates"] = len(creates)
    summary["exists"] = len(site.get("exists", []))
    summary["unresolved"] = len(site.get("unresolved", []))

    return {
        "changed_players": len(changed_ids),
        "added_transfers": added_transfers,
        "updated_transfers": updated_transfers,
        "returned_to_base": returned_to_base,
        "review_items": review_items,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily FC26 Transfermarkt roster refresh")
    parser.add_argument("--teams", type=Path, default=DEFAULT_TEAMS)
    parser.add_argument("--identities", type=Path, default=DEFAULT_IDENTITIES)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--delay", type=float, default=1.15)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--min-success-ratio", type=float, default=0.85)
    parser.add_argument("--limit", type=int, default=0, help="Development only")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def validate_inputs(args: argparse.Namespace) -> None:
    teams = load_json(args.teams)
    identities = load_json(args.identities)
    state = load_json(args.state)
    site = load_json(args.output)
    if not isinstance(teams.get("teams"), list) or not teams["teams"]:
        raise RuntimeError("Takım eşleme verisi boş")
    if not isinstance(identities.get("players"), dict) or not identities["players"]:
        raise RuntimeError("FC26 kimlik verisi boş")
    if not isinstance(state.get("teams"), dict) or not state["teams"]:
        raise RuntimeError("Başlangıç kadro görüntüsü boş")
    if not isinstance(site.get("transfers"), list):
        raise RuntimeError("Yayın verisinde transfers listesi yok")
    print(
        f"Doğrulandı: {len(teams['teams'])} takım, "
        f"{len(identities['players'])} FC26 oyuncusu, "
        f"{len(state['teams'])} kadro görüntüsü"
    )


def main() -> int:
    args = parse_args()
    validate_inputs(args)
    if args.validate_only:
        return 0

    teams_document = load_json(args.teams)
    teams = [team for team in teams_document["teams"] if not team.get("generic_or_unlicensed")]
    if args.limit > 0:
        teams = teams[: args.limit]

    identities = load_json(args.identities)
    old_state = load_json(args.state)
    site = load_json(args.output)
    new_state = json.loads(json.dumps(old_state))
    new_state["schema_version"] = 1
    checked_at = utc_now()
    new_state["checked_at"] = checked_at

    session = create_session()
    failures: list[str] = []
    successes = 0

    for index, team in enumerate(teams, start=1):
        team_id = str(team["fc_team_id"])
        try:
            url, players = fetch_roster(session, team, max(1, args.retries))
            new_state.setdefault("teams", {})[team_id] = {
                "fc_team_id": team_id,
                "fc_team_name": clean(team["fc_team_name"]),
                "tm_id": str(team["tm_id"]),
                "tm_name": clean(team["tm_name"]),
                "slug": clean(team["slug"]),
                "url": url,
                "checked_at": checked_at,
                "players": players,
            }
            successes += 1
            print(f"[{index}/{len(teams)}] OK {team['fc_team_name']}: {len(players)}")
        except Exception as exc:
            failures.append(str(exc))
            print(f"[{index}/{len(teams)}] HATA {exc}")

        if index < len(teams):
            time.sleep(max(0.0, args.delay) + random.uniform(0.0, 0.25))

    success_ratio = successes / max(len(teams), 1)
    if success_ratio < args.min_success_ratio:
        raise RuntimeError(
            f"Yayın iptal: başarı oranı %{success_ratio * 100:.1f}; "
            f"gerekli en az %{args.min_success_ratio * 100:.1f}"
        )

    changes = reconcile(site, identities, old_state, new_state)
    site["last_checked_at"] = checked_at
    site["data_source"] = "Transfermarkt public club rosters"
    site["daily_refresh"] = {
        **changes,
        "teams_checked": len(teams),
        "teams_succeeded": successes,
        "teams_failed": len(failures),
    }

    write_json_atomic(args.state, new_state)
    write_json_atomic(args.output, site)
    print(json.dumps(site["daily_refresh"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
