from custom_components.rootine.logic import profile as pr
from custom_components.rootine.logic.texts import TextItem, item_text, summary_text, task_verb

OPB = {
    "pid": "coffea arabica",
    "display_pid": "Coffea arabica",
    "alias": "Arabica-Kaffee",
    "image_url": "https://opb-img.plantbook.io/coffea_arabica.jpg",
    "common_names": [
        {"name": "Coffee", "language_code": "en"},
        {"name": "Kaffeestrauch", "language_code": "de"},
    ],
    "watering": "Alle 5-7 Tage",
    "fertilization": "Alle 2-4 Wochen",
    "min_temp": 15,
    "max_temp": 27,
    "min_soil_moist": 25,
}


def test_parse_opb():
    d = pr.parse_opb(OPB)
    assert d["common_name"] == "Kaffeestrauch"
    assert d["species"] == "Coffea arabica"
    assert d["care.watering"] == "Alle 5-7 Tage"
    assert "care.soil" not in d
    assert d["hint_temp"] == (15, 27)
    no_de = dict(OPB, common_names=[{"name": "Coffee", "language_code": "en"}])
    assert pr.parse_opb(no_de)["common_name"] == "Arabica-Kaffee"
    assert pr.parse_opb({"pid": "x", "display_pid": "X x"})["common_name"] == "X x"


def test_apply_opb_keeps_manual():
    base = pr.apply_opb(pr.Profile(), pr.parse_opb(OPB))
    assert base.common_name == "Kaffeestrauch"
    assert base.opb_pid == "coffea arabica"
    edited = pr.update_fields(base, {"common_name": "Kaffee", "care.watering": "Mein Plan"})
    assert edited.manual_fields == {"common_name", "care.watering"}
    new = dict(OPB, watering="Neu", fertilization="Neu2")
    again = pr.apply_opb(edited, pr.parse_opb(new))
    assert again.common_name == "Kaffee"
    assert again.care["watering"] == "Mein Plan"
    assert again.care["fertilization"] == "Neu2"
    forced = pr.apply_opb(edited, pr.parse_opb(new), overwrite_manual=True)
    assert forced.common_name == "Kaffeestrauch"
    assert forced.care["watering"] == "Neu"
    assert forced.manual_fields == set()
    assert edited.common_name == "Kaffee"  # input unchanged


def test_update_fields_empty_deletes_and_marks():
    p = pr.apply_opb(pr.Profile(), pr.parse_opb(OPB))
    p = pr.update_fields(p, {"care.watering": "", "cultivar": "X"})
    assert "watering" not in p.care
    assert p.cultivar == "X"
    again = pr.apply_opb(p, pr.parse_opb(OPB))
    assert "watering" not in again.care  # stays cleared


def test_from_form():
    prefilled = {"common_name": "Kaffeestrauch", "species": "Coffea arabica", "pot": None}
    submitted = {"common_name": "Kaffee", "species": "Coffea arabica", "pot": "", "cultivar": "A"}
    p = pr.from_form(submitted, prefilled)
    assert p.manual_fields == {"common_name", "cultivar"}
    by_hand = pr.from_form({"common_name": "Kaffee", "pot": ""})
    assert by_hand.manual_fields == {"common_name"}
    assert by_hand.pot is None


def test_unlink():
    p = pr.apply_opb(pr.Profile(), pr.parse_opb(OPB))
    u = pr.unlink(p)
    assert u.opb_pid is None and u.opb_image_url is None
    assert u.common_name == "Kaffeestrauch"
    assert {"common_name", "species", "care.watering"} <= u.manual_fields
    assert (
        pr.apply_opb(u, pr.parse_opb(dict(OPB, watering="Neu"))).care["watering"] == "Alle 5-7 Tage"
    )


def test_photo_url_chain():
    p = pr.Profile(opb_image_url="https://x/y.jpg")
    assert pr.photo_url(p) == "https://x/y.jpg"
    p.photo = "media-source://image_upload/01ABC"
    assert pr.photo_url(p) == "/api/image/serve/01ABC/512x512"
    p.photo = "media-source://media_source/local/foo.jpg"
    assert pr.photo_url(p) == "https://x/y.jpg"
    p.photo = "media-source://image_upload/../evil"
    assert pr.photo_url(p) == "https://x/y.jpg"
    assert pr.photo_url(pr.Profile()) is None


def test_verbs():
    assert task_verb("Gießen") == "gießen"
    assert task_verb("Düngen") == "düngen"
    assert task_verb("Spinnmilben-Check") == "Spinnmilben-Check erledigen"


def test_item_texts():
    T = TextItem
    assert item_text(T("Satsuma", "water", "Gießen", "due")) == "Satsuma: Gießen ist heute fällig."
    assert (
        item_text(T("Kirsche", "water", "Gießen", "overdue", days=2))
        == "Kirsche: Gießen ist seit 2 Tagen überfällig."
    )
    assert "seit 1 Tag überfällig" in item_text(T("K", "water", "Gießen", "overdue", days=1))
    assert item_text(T("Kaffee", "fertilize", "Düngen", "soon")) == (
        "Kaffee: Düngen ist morgen fällig."
    )
    assert item_text(T("Nektarine", "sensor_check", "", "check_sensor", reason="drop")) == (
        "Nektarine: Sensor prüfen, der Wert ist plötzlich stark gefallen."
    )
    assert item_text(T("Nektarine", "sensor_check", "", "check_sensor", reason="battery_low")) == (
        "Nektarine: Sensor-Batterie schwach."
    )
    assert item_text(T("Satsuma", "protect", "", "protect", reason="cold_forecast", value=2)) == (
        "Satsuma: Frost erwartet, heute Nacht bis 2 Grad. Reinholen oder schützen."
    )
    assert item_text(T("Kaffee", "protect", "", "protect", reason="cold_now", value=13)) == (
        "Kaffee: zu kalt, gemessen 13 Grad."
    )
    assert item_text(T("Kirsche", "protect", "", "protect", reason="heat_forecast", value=34)) == (
        "Kirsche: Hitze erwartet, bis 34 Grad. Schatten und genug Wasser."
    )
    assert item_text(T("Satsuma", "too_wet", "", "too_wet", days=2)) == (
        "Satsuma: seit 2 Tagen sehr nass."
    )


def test_summary():
    T = TextItem
    items = [
        T("Satsuma", "water", "Gießen", "due"),
        T("Kaffee", "fertilize", "Düngen", "due"),
        T("Kirsche", "water", "Gießen", "overdue", days=3),
        T("Basilikum", "water", "Gießen", "soon"),
    ]
    assert summary_text(items) == (
        "Heute zu tun: Satsuma gießen, Kaffee düngen. Überfällig: Kirsche gießen. "
        "Morgen: Basilikum gießen."
    )
    assert summary_text([]) == "Heute ist nichts zu tun."


def test_more_texts():
    T = TextItem
    assert item_text(T("A", "protect", "", "protect", reason="cold_forecast", value=4)) == (
        "A: Kälte erwartet, heute Nacht bis 4 Grad. Reinholen oder schützen."
    )
    assert item_text(T("A", "protect", "", "protect", reason="cold_now", value=-2)) == (
        "A: zu kalt, gemessen minus 2 Grad."
    )
    assert item_text(T("A", "protect", "", "protect", reason="heat_now", value=36)) == (
        "A: zu heiß, gemessen 36 Grad."
    )
    assert item_text(T("A", "protect", "", "protect")) == "A: Schutz nötig."
    assert item_text(T("A", "s", "", "check_sensor", reason="stale")).startswith("A: Sensor prüfen")
    assert item_text(T("A", "s", "", "check_sensor")) == "A: Sensor prüfen."
    assert item_text(T("A", "w", "", "too_wet")) == "A: sehr nass."
    assert item_text(T("A", "water", "Gießen", "ok")) == "A: Gießen ist in Ordnung."
    warn = summary_text([T("A", "protect", "", "protect", reason="cold_now", value=1)])
    assert warn == "A: zu kalt, gemessen 1 Grad."


def test_upcoming_texts():
    T = TextItem
    item = T("Kaffee", "water", "Gießen", "ok", in_days=3)
    assert item_text(item) == "Kaffee: Gießen ist in 3 Tagen fällig."
    assert summary_text([item]) == "Demnächst: Kaffee gießen (in 3 Tagen)."
    assert item_text(T("Kaffee", "water", "Gießen", "soon", in_days=1)) == (
        "Kaffee: Gießen ist morgen fällig."
    )
