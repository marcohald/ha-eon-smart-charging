# E.ON Smart Charging Home Assistant Integration

Custom Component für Home Assistant zur Steuerung des E.ON Smart-Lademodus (rabattiertes Laden), Sofortladens und aller Ladeparameter für Elektroautos (z. B. Dacia Spring via CarConnect) und smarte E.ON Wallboxen.

---

## Funktionen

* **Lademodus-Auswahl (`select.eon_smart_charging_lademodus`):**
  * `Smart Laden (Autopilot)`: Aktiviert den intelligenten, rabattierten Lade-Algorithmus von E.ON.
  * `Normal Laden (Sofort)`: Lädt das Fahrzeug sofort mit maximal verfügbarer Leistung ohne Tarifoptimierung.
  * `Aus`: Pausiert/deaktiviert die automatische Ladesteuerung.
* **Schalter (`switch.eon_smart_charging_*`):**
  * `Smart Laden`: Schalter zum direkten Aktivieren/Deaktivieren des Smart-Lademodus.
  * `Normales Laden (Sofort)`: Schalter zum direkten Starten/Stoppen des Schnellladens.
* **Abfahrtszeit (`time.eon_smart_charging_abfahrtszeit`):**
  * Konfigurierbare Uhrzeit (z. B. `07:00`), bis zu der das Fahrzeug den Zielladestand erreicht haben muss.
* **Ladeziel (`number.eon_smart_charging_ladeziel_ziel_soc`):**
  * Schieberegler von 50 % bis 100 % (Standard: 80 %).
* **Mindestladestand (`number.eon_smart_charging_mindestladestand_min_soc`):**
  * Sofort zu ladender Mindestpuffer (10 % bis 50 %, Standard: 20 %).
* **Sensoren (`sensor.eon_smart_charging_*`):**
  * Aktiver Modus & Statusbeschreibung.
  * Ladekabel-Verbindungsstatus.

---

## Einrichtung in Home Assistant (Keine Tokens nötig!)

Die Integration nutzt den offiziellen **E.ON OAuth 2.0 PKCE Flow**. Du musst keine internen Tokens mehr manuell suchen:

1. Gehe in Home Assistant auf **Einstellungen -> Geräte & Dienste -> Integration hinzufügen**.
2. Wähle **E.ON Smart Charging**.
3. Ein Dialog öffnet sich mit einem Login-Link:
   * Klicke auf den angezeigten Link **"Hier klicken: Bei E.ON anmelden"**.
   * Melde dich in deinem Webbrowser mit deinen regulären E.ON Zugangsdaten an.
4. Nach dem Login leitet der Browser auf eine URL weiter, die mit `meineonandroid://` beginnt:
   * Kopiere diese komplette Adresse aus der Adresszeile (z. B. `meineonandroid://auth/success/auth0?code=...`).
   * Füge sie in das Eingabefeld in Home Assistant ein und klicke auf **Senden**.
5. Home Assistant tauscht den Code automatisch gegen alle benötigten Tokens ein und richtet den automatischen Token-Refresh im Hintergrund ein.
6. Wähle im nächsten Schritt dein Fahrzeug (z. B. Dacia Spring) oder deine Wallbox aus – fertig!

---

## Automations-Beispiele

### 1. Dynamische Abfahrtszeit anhand des Weckers oder Kalenders setzen
```yaml
alias: "E.ON: Abfahrtszeit an Kalender anpassen"
trigger:
  - platform: time
    at: "20:00:00"
action:
  - service: time.set_value
    target:
      entity_id: time.eon_smart_charging_abfahrtszeit
    data:
      time: "06:30:00"
```

### 2. Bei negativen Strompreisen auf Sofortladen schalten
```yaml
alias: "E.ON: Bei negativen Börsenpreisen sofort voll laden"
trigger:
  - platform: numeric_state
    entity_id: sensor.electricity_price
    below: 0.00
action:
  - service: select.select_option
    target:
      entity_id: select.eon_smart_charging_lademodus
    data:
      option: "Normal Laden (Sofort)"
```

### 3. Abends automatisch in den Smart-Lademodus versetzen
```yaml
alias: "E.ON: Abends Smart Laden aktivieren"
trigger:
  - platform: time
    at: "22:00:00"
condition:
  - condition: state
    entity_id: sensor.eon_smart_charging_kabelstatus
    state: "Angesteckt"
action:
  - service: select.select_option
    target:
      entity_id: select.eon_smart_charging_lademodus
    data:
      option: "Smart Laden (Autopilot)"
```
