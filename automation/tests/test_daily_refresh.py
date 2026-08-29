import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "daily_refresh.py"
SPEC = importlib.util.spec_from_file_location("daily_refresh", MODULE_PATH)
daily = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(daily)


class DailyRefreshTests(unittest.TestCase):
    def test_parse_roster_html(self):
        rows = "".join(
            f'<tr><td><a title="Oyuncu {i}" href="/oyuncu-{i}/profil/spieler/{1000+i}">x</a></td></tr>'
            for i in range(10)
        )
        page = f'<html><table class="items"><tbody>{rows}</tbody></table></html>'
        players = daily.parse_roster_html(page)
        self.assertEqual(10, len(players))
        self.assertEqual("1000", players[0]["tm_id"])
        self.assertEqual("Oyuncu 0", players[0]["name"])

    def test_reconcile_safe_transfer(self):
        site = {
            "summary": {},
            "transfers": [],
            "creates": [],
            "exists": [],
            "unresolved": [],
        }
        identities = {
            "players": {
                "42": {
                    "name": "Test Oyuncu",
                    "team_ids": ["1"],
                    "team_names": ["Eski Takım"],
                }
            }
        }
        old_state = {
            "teams": {
                "1": {
                    "fc_team_name": "Eski Takım",
                    "players": [{"tm_id": "99", "name": "Test Oyuncu"}],
                },
                "2": {"fc_team_name": "Yeni Takım", "players": []},
            }
        }
        new_state = {
            "teams": {
                "1": {"fc_team_name": "Eski Takım", "players": []},
                "2": {
                    "fc_team_name": "Yeni Takım",
                    "players": [{"tm_id": "99", "name": "Test Oyuncu"}],
                },
            }
        }
        result = daily.reconcile(site, identities, old_state, new_state)
        self.assertEqual(1, result["added_transfers"])
        self.assertEqual("42", site["transfers"][0]["fc_id"])
        self.assertEqual("Yeni Takım", site["transfers"][0]["target"])

    def test_reconcile_returns_to_base(self):
        site = {
            "summary": {},
            "transfers": [
                {
                    "key": "TRANSFER|42|99|Yeni Takım",
                    "fc_id": "42",
                    "tm_id": "99",
                    "player": "Test Oyuncu",
                    "source": "Eski Takım",
                    "target": "Yeni Takım",
                }
            ],
            "creates": [],
            "exists": [],
            "unresolved": [],
        }
        identities = {
            "players": {
                "42": {
                    "name": "Test Oyuncu",
                    "team_ids": ["1"],
                    "team_names": ["Eski Takım"],
                }
            }
        }
        old_state = {
            "teams": {
                "1": {"fc_team_name": "Eski Takım", "players": []},
                "2": {
                    "fc_team_name": "Yeni Takım",
                    "players": [{"tm_id": "99", "name": "Test Oyuncu"}],
                },
            }
        }
        new_state = {
            "teams": {
                "1": {
                    "fc_team_name": "Eski Takım",
                    "players": [{"tm_id": "99", "name": "Test Oyuncu"}],
                },
                "2": {"fc_team_name": "Yeni Takım", "players": []},
            }
        }
        result = daily.reconcile(site, identities, old_state, new_state)
        self.assertEqual(1, result["returned_to_base"])
        self.assertEqual([], site["transfers"])


if __name__ == "__main__":
    unittest.main()
