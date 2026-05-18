"""
tests fuer nina_mc.py
=====================
Unit Tests fuer Titel-Kuerzung und Nachrichtenformatierung.
Laufen lokal ohne RPi/Companion.

Ausfuehren: python3 -m unittest test_nina_mc -v
"""

import unittest
from unittest.mock import patch, MagicMock

# nina_mc importieren - Logfile auf lokales /tmp umbiegen
import logging
import unittest.mock
_tmp_handler = logging.FileHandler("/tmp/nina_mc_test.log")
with unittest.mock.patch("logging.FileHandler", return_value=_tmp_handler):
    import nina_mc


class TestShortenTitle(unittest.TestCase):

    def test_kuerzt_langen_titel(self):
        title = "Hochwasserwarnung fuer das gesamte Stadtgebiet Gifhorn und alle umliegenden Ortschaften"
        result = nina_mc.shorten_title(title)
        self.assertLessEqual(len(result), nina_mc.MAX_TITLE + 3)  # +3 fuer "..."
        self.assertTrue(result.endswith("..."))

    def test_kurzer_titel_unveraendert(self):
        title = "Hochwasser Gifhorn"
        self.assertEqual(nina_mc.shorten_title(title), title)

    def test_entfernt_aktualisierung_prefix(self):
        title = "3. Aktualisierung! - Hochwasser Gifhorn"
        self.assertEqual(nina_mc.shorten_title(title), "Hochwasser Gifhorn")

    def test_entfernt_aktualisierung_ohne_ausrufezeichen(self):
        title = "2. Aktualisierung - Trinkwasserwarnung"
        self.assertEqual(nina_mc.shorten_title(title), "Trinkwasserwarnung")

    def test_entwarnung_prefix_bleibt_in_shorten_title(self):
        # shorten_title entfernt "Entwarnung:" NICHT mehr — das macht format_warning
        title = "Entwarnung: Gasaustritt Gifhorn-Nord"
        self.assertEqual(nina_mc.shorten_title(title), "Entwarnung: Gasaustritt Gifhorn-Nord")

    def test_kein_wortabriss_beim_kuerzen(self):
        # Titel soll an Wortgrenze gekuerzt werden, nicht mitten im Wort
        title = "A" * 55 + " Wort das abgeschnitten werden wuerde"
        result = nina_mc.shorten_title(title)
        self.assertTrue(result.endswith("..."))
        self.assertFalse(result.endswith("W..."))  # kein halbes Wort


class TestFormatWarning(unittest.TestCase):

    def _make_warning(self, wtype, severity, title_de):
        return {
            "id": "test-123",
            "type": wtype,
            "severity": severity,
            "i18nTitle": {"de": title_de}
        }

    def test_alert_format(self):
        w = self._make_warning("Alert", "Severe", "Hochwasser Gifhorn")
        result = nina_mc.format_warning(w, "gf")
        self.assertEqual(result, "[nina gf] alert/severe: Hochwasser Gifhorn")

    def test_update_format(self):
        w = self._make_warning("Update", "Minor", "Trinkwasserwarnung")
        result = nina_mc.format_warning(w, "wob")
        self.assertEqual(result, "[nina wob] update/minor: Trinkwasserwarnung")

    def test_cancel_via_type(self):
        # type=cancel → entwarnung
        w = self._make_warning("Cancel", "Minor", "Gasaustritt Gifhorn-Nord")
        result = nina_mc.format_warning(w, "gf")
        self.assertEqual(result, "[nina gf] entwarnung: Gasaustritt Gifhorn-Nord")

    def test_cancel_via_titel_prefix(self):
        # BBK sendet nicht immer type=cancel — Erkennung auch ueber Titel
        w = self._make_warning("Update", "Minor", "Entwarnung: Gasaustritt Gifhorn-Nord")
        result = nina_mc.format_warning(w, "gf")
        self.assertEqual(result, "[nina gf] entwarnung: Gasaustritt Gifhorn-Nord")

    def test_entwarnung_prefix_wird_aus_titel_entfernt(self):
        # "Entwarnung: " soll nicht doppelt erscheinen
        w = self._make_warning("Cancel", "Minor", "Entwarnung: Rauchgas Gifhorn")
        result = nina_mc.format_warning(w, "gf")
        self.assertEqual(result, "[nina gf] entwarnung: Rauchgas Gifhorn")
        self.assertNotIn("entwarnung: entwarnung", result.lower())

    def test_leerer_type_und_severity_fallback(self):
        # Wenn type/severity leer → "warnung:" statt "/:"
        w = self._make_warning("", "", "Rauchgasausbreitung Gifhorn")
        result = nina_mc.format_warning(w, "gf")
        self.assertEqual(result, "[nina gf] warnung: Rauchgasausbreitung Gifhorn")
        self.assertNotIn("/:", result)

    def test_fehlender_titel_fallback(self):
        w = {"id": "x", "type": "Alert", "severity": "Severe", "i18nTitle": {}}
        result = nina_mc.format_warning(w, "bs")
        self.assertIn("unbekannte warnung", result)

    def test_prefix_wird_lowercase_gesendet(self):
        # send_mesh macht .lower() — hier pruefen wir format_warning direkt
        w = self._make_warning("Alert", "Extreme", "Test")
        result = nina_mc.format_warning(w, "gf")
        self.assertIn("[nina gf]", result)
        self.assertIn("alert/extreme", result)


class TestFetchWarnings(unittest.TestCase):

    @patch("nina_mc.requests.get")
    def test_gibt_liste_zurueck(self, mock_get):
        mock_get.return_value.json.return_value = [{"id": "w1"}, {"id": "w2"}]
        mock_get.return_value.raise_for_status = MagicMock()
        result = nina_mc.fetch_warnings("031510000000", "gf")
        self.assertEqual(len(result), 2)

    @patch("nina_mc.requests.get")
    def test_gibt_leere_liste_bei_keine_warnungen(self, mock_get):
        mock_get.return_value.json.return_value = []
        mock_get.return_value.raise_for_status = MagicMock()
        result = nina_mc.fetch_warnings("031510000000", "gf")
        self.assertEqual(result, [])

    @patch("nina_mc.send_room")
    @patch("nina_mc.requests.get")
    def test_gibt_none_bei_api_fehler(self, mock_get, mock_room):
        mock_get.side_effect = Exception("connection error")
        result = nina_mc.fetch_warnings("031510000000", "gf")
        self.assertIsNone(result)

    @patch("nina_mc.send_room")
    @patch("nina_mc.requests.get")
    def test_sendet_room_meldung_bei_fehler(self, mock_get, mock_room):
        mock_get.side_effect = Exception("timeout")
        nina_mc.fetch_warnings("031510000000", "gf")
        mock_room.assert_called_once()
        self.assertIn("fehler", mock_room.call_args[0][0])


class TestDoppelmeldungVerhindern(unittest.TestCase):
    """Stellt sicher dass bekannte Warnungen nicht erneut gesendet werden."""

    @patch("nina_mc.send_mesh")
    @patch("nina_mc.requests.get")
    def test_bekannte_warnung_nicht_nochmal_senden(self, mock_get, mock_send):
        warnung = {"id": "w-001", "type": "Alert", "severity": "Severe",
                   "i18nTitle": {"de": "Hochwasser"}}
        mock_get.return_value.json.return_value = [warnung]
        mock_get.return_value.raise_for_status = MagicMock()

        seen = {"031510000000": {"w-001"}}  # bereits bekannt

        warnings = nina_mc.fetch_warnings("031510000000", "gf")
        current_ids = {w["id"] for w in warnings}
        for w in warnings:
            if w["id"] not in seen["031510000000"]:
                nina_mc.send_mesh(nina_mc.format_warning(w, "gf"))

        mock_send.assert_not_called()

    @patch("nina_mc.send_mesh")
    @patch("nina_mc.requests.get")
    def test_neue_warnung_wird_gesendet(self, mock_get, mock_send):
        warnung = {"id": "w-002", "type": "Alert", "severity": "Severe",
                   "i18nTitle": {"de": "Hochwasser"}}
        mock_get.return_value.json.return_value = [warnung]
        mock_get.return_value.raise_for_status = MagicMock()

        seen = {"031510000000": set()}  # noch nichts bekannt

        warnings = nina_mc.fetch_warnings("031510000000", "gf")
        for w in warnings:
            if w["id"] not in seen["031510000000"]:
                nina_mc.send_mesh(nina_mc.format_warning(w, "gf"))

        mock_send.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
