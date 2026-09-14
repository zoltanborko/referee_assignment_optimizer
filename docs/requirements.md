# Játékvezetői küldés optimalizáló rendszer

## 1. A projekt célja

A projekt célja egy webalapú döntéstámogató rendszer fejlesztése, amely
segíti a Hajdú-Bihar vármegyei amatőr labdarúgó-mérkőzések
játékvezetőinek hozzárendelését.

A jelenlegi manuális folyamat során a küldő személy tapasztalat alapján
rendeli hozzá a játékvezetőket az egyes mérkőzésekhez. A rendszer célja
ennek támogatása egy olyan optimalizálási módszerrel, amely figyelembe
veszi a szakmai és technikai feltételeket, valamint az utazási
távolságokat és költségeket.

A rendszer nem feltétlenül helyettesíti a küldő személy döntését, hanem
döntéstámogató eszközként javasolt hozzárendelést készít.

---

## 2. A rendszer hatóköre

### A rendszer feladatai

- Játékvezetői adatok kezelése.
- Mérkőzések adatainak kezelése.
- Mérkőzésadatok importálása megfelelő formátumból.
- A játékvezetők mérkőzésekhez történő hozzárendelése.
- Szakmai és technikai feltételek ellenőrzése.
- Utazási távolságok figyelembevétele.
- Optimalizált vagy költséghatékony küldés előállítása.
- A generált küldés megjelenítése.
- Az eredmények exportálása vagy mentése.

### A rendszer kezdeti hatókörén kívül eső feladatok

- Játékvezetők automatikus értesítése.
- Hivatalos küldés automatikus közzététele.
- Fizetések és elszámolások kezelése.
- Valós idejű GPS-alapú útvonaltervezés.
- Forgalmi adatok figyelembevétele.
- Teljes körű felhasználó- és jogosultságkezelés.

Ezek későbbi továbbfejlesztési lehetőségek lehetnek.

---

## 3. Felhasználói szerepkör

### Küldő / rendszerhasználó

A rendszer elsődleges felhasználója a játékvezetők mérkőzésekhez
történő hozzárendelésével foglalkozó személy.

A felhasználó feladatai:

- Játékvezetők adatainak megtekintése és kezelése.
- Mérkőzések adatainak feltöltése vagy rögzítése.
- Az optimalizálási folyamat elindítása.
- A generált küldés ellenőrzése.
- Az eredmény szükség esetén történő módosítása vagy exportálása.

---

## 4. Bemeneti adatok

### 4.1. Játékvezetők

A rendszernek a játékvezetőkről legalább az alábbi adatokat kell
kezelnie:

| Mező | Leírás | Kötelező |
|---|---|---|
| `id` | Egyedi azonosító | Igen |
| `name` | Játékvezető neve | Igen |
| `residence` | Lakóhely / kiindulási település | Igen |
| `cadre` | Kerettagság vagy kategória | Igen |
| `has_car` | Rendelkezik-e autóval | Igen |

Lehetséges keretkategóriák például:

- Megye 1
- Megye 2
- Megye 3
- Egyéb

A kategóriák pontos jelentését és a hozzárendelési szabályokat a
szakmai követelmények alapján kell véglegesíteni.

### 4.2. Mérkőzések

A rendszernek a mérkőzésekről legalább az alábbi adatokat kell
kezelnie:

| Mező | Leírás | Kötelező |
|---|---|---|
| `id` | Egyedi mérkőzésazonosító | Igen |
| `date` | Mérkőzés dátuma | Igen |
| `time` | Mérkőzés kezdési időpontja | Igen |
| `location` | Mérkőzés helyszíne / települése | Igen |
| `required_referees` | Szükséges játékvezetők száma | Igen |
| `required_cadre` | Elvárt keret vagy kategória | A szabályoktól függ |

További, később szükségessé váló mezők:

- Hazai csapat.
- Vendégcsapat.
- Pálya neve.
- Mérkőzés típusa.
- Egyéb szakmai követelmények.

### 4.3. Távolságadatok

A rendszernek szüksége van a játékvezetők kiindulási helye és a
mérkőzések helyszíne közötti távolságokra.

A távolságadatok kezdetben előre rögzített adatokból is származhatnak.

A tervezett településhálózatban:

- A csúcsok a települések.
- Az élek a települések közötti utak.
- Az élek súlyai az utakhoz tartozó távolságok.

A távolságok meghatározásának pontos módját a megvalósítás során kell
véglegesíteni.

---

## 5. Funkcionális követelmények

### FR-01: Játékvezetők kezelése

A rendszer tegye lehetővé a játékvezetői adatok létrehozását,
megtekintését, módosítását és törlését.

### FR-02: Mérkőzések kezelése

A rendszer tegye lehetővé a mérkőzések adatainak rögzítését,
megtekintését, módosítását és törlését.

### FR-03: Mérkőzések importálása

A rendszer tegye lehetővé mérkőzésadatok feltöltését egy előre
meghatározott formátumú fájlból.

A rendszernek ellenőriznie kell:

- A kötelező mezők meglétét.
- Az adatok megfelelő formátumát.
- Az azonosítók egyediségét.
- A hibás vagy hiányos adatok jelenlétét.

### FR-04: Játékvezetői jogosultságok ellenőrzése

A rendszer csak olyan játékvezetőt rendelhessen mérkőzéshez, aki
megfelel az adott mérkőzéshez meghatározott szakmai feltételeknek.

Ilyen feltétel lehet például:

- Keretkategória.
- Autó megléte.
- Egyéb, a küldés szabályai által meghatározott feltétel.

### FR-05: Időbeli ütközések ellenőrzése

A rendszer ne rendeljen ugyanahhoz a játékvezetőhöz olyan mérkőzéseket,
amelyeken időben nem tudna részt venni.

A pontos időbeli és utazási korlátozások meghatározása a részletes
tervezés során történik.

### FR-06: Optimalizálás indítása

A felhasználó indíthassa el az optimalizálási folyamatot a megadott
mérkőzések és játékvezetők alapján.

### FR-07: Optimalizált hozzárendelés előállítása

A rendszer állítson elő egy olyan hozzárendelést, amely:

- Teljesíti a megadott kötelező feltételeket.
- A lehetőségekhez mérten csökkenti az utazással kapcsolatos költséget
  vagy távolságot.
- Jelzi, ha nem található minden feltételnek megfelelő megoldás.

### FR-08: Eredmény megjelenítése

A rendszer jelenítse meg a generált küldést legalább az alábbi
információkkal:

- Mérkőzés.
- Hozzárendelt játékvezető.
- Játékvezető kiindulási helye.
- Mérkőzés helyszíne.
- Számított utazási távolság.
- Esetleges figyelmeztetések.

### FR-09: Eredmény mentése vagy exportálása

A felhasználó menthesse vagy exportálhassa a generált küldést
feldolgozható formátumban.

A támogatott formátumot a megvalósítás során kell véglegesíteni.

### FR-10: Hibák és figyelmeztetések kezelése

A rendszer adjon érthető visszajelzést például az alábbi esetekben:

- Hiányos bemeneti adatok.
- Hibás fájlformátum.
- Nem megfelelő keretkategória.
- Nincs elegendő játékvezető.
- Nincs minden mérkőzéshez érvényes hozzárendelés.
- Nem található megoldás a megadott korlátozások mellett.

---

## 6. Optimalizálási követelmények

### 6.1. Optimalizálási cél

A rendszer elsődleges optimalizálási célja a játékvezetők és
mérkőzések közötti hozzárendelés során felmerülő utazási távolságok
vagy költségek csökkentése.

A célfüggvény pontos formáját a matematikai modell kidolgozásakor kell
meghatározni.

### 6.2. Alapvető korlátozások

A rendszernek figyelembe kell vennie legalább az alábbi korlátozásokat:

- Minden mérkőzéshez a szükséges számú játékvezető legyen rendelve.
- Csak megfelelő szakmai kategóriájú játékvezető legyen hozzárendelhető.
- Egy játékvezető ne legyen egyszerre több, időben ütköző mérkőzéshez
  rendelve.
- A technikai feltételeknek megfelelő játékvezetők kerüljenek
  kiválasztásra.
- A hozzárendelés legyen konzisztens és ellenőrizhető.

### 6.3. Megoldhatatlanság kezelése

Ha a megadott feltételek mellett nem készíthető teljes hozzárendelés,
a rendszer:

- Jelezze, hogy nincs teljes megoldás.
- Lehetőség szerint azonosítsa a problémás mérkőzéseket.
- Adjon értelmezhető visszajelzést a felhasználónak.

A részleges megoldás előállítása opcionális, és a későbbi tervezés
során döntendő el.

---

## 7. Nem funkcionális követelmények

### NFR-01: Webes elérhetőség

A rendszer webes felületen keresztül legyen használható.

### NFR-02: Platformfüggetlenség

A rendszer kliensoldali felülete modern webböngészőből, külön telepítés
nélkül legyen elérhető.

### NFR-03: Használhatóság

A felület legyen áttekinthető, és a felhasználó számára egyértelműen
jelezze a bemenetek, az optimalizálás és az eredmények állapotát.

### NFR-04: Bővíthetőség

A rendszer felépítése tegye lehetővé új optimalizálási feltételek,
adatmezők és funkciók későbbi hozzáadását.

### NFR-05: Tesztelhetőség

Az optimalizáló modul működése külön is tesztelhető legyen a webes
felülettől függetlenül.

### NFR-06: Adatkonzisztencia

A rendszer ellenőrizze a bemeneti adatok érvényességét, és ne engedjen
érvénytelen vagy ellentmondásos hozzárendelést.

### NFR-07: Teljesítmény

A rendszer a tervezett felhasználási méret mellett elfogadható időn
belül készítsen optimalizált hozzárendelést.

A pontos teljesítménykövetelményeket a tesztelési szakaszban kell
meghatározni.

---

## 8. MVP (Minimum Viable Product)

Az első működő változat célja egy korlátozott, de teljes folyamatot
végrehajtani képes rendszer létrehozása.

### Az MVP tartalma

- Játékvezetők betöltése JSON-fájlból.
- Mérkőzések betöltése JSON-fájlból.
- Alapvető adatok validálása.
- Előre rögzített távolságadatok használata.
- Alapvető szakmai korlátozások kezelése.
- Optimalizáló algoritmus futtatása.
- Generált hozzárendelés megjelenítése.
- Hibás vagy megoldhatatlan esetek jelzése.

### Az MVP-ből kezdetben kimaradó funkciók

- Teljes körű adminisztrációs felület.
- Felhasználói bejelentkezés.
- Automatikus térképes útvonaltervezés.
- Valós idejű forgalmi adatok.
- Automatikus értesítések.
- Összetett jogosultságkezelés.
- Többféle optimalizálási cél egyidejű kezelése.

---

## 9. Nyitott kérdések

A fejlesztés megkezdése előtt vagy közben az alábbi kérdéseket
véglegesíteni kell:

1. Pontosan milyen keretkategóriák és hozzárendelési szabályok
   érvényesek?
2. Egy mérkőzéshez pontosan hány játékvezető szükséges?
3. A játékvezető saját lakóhelyéről indul, vagy más kiindulási helyet
   kell figyelembe venni?
4. A cél az egyirányú vagy az oda-vissza utazási távolság minimalizálása?
5. A költség a távolságból számítandó, vagy külön üzemanyagköltség-modell
   szükséges?
6. Figyelembe kell-e venni az egymást követő mérkőzések közötti utazást?
7. Lehetséges-e egy játékvezetőnek több mérkőzést kiosztani egy napon?
8. Milyen formátumból történjen a mérkőzések importálása?
9. Szükséges-e a meglévő Excel-fájlok közvetlen támogatása?
10. Milyen esetekben fogadható el részleges megoldás?
11. Milyen formátumban kell exportálni a kész küldést?
12. Mekkora adatmennyiséggel kell a rendszert tesztelni?
13. Milyen optimalizáló könyvtár vagy solver használata indokolt?
14. Szükséges-e a rendszerhez adatbázis, vagy elegendő a fájlalapú
    adattárolás?

---

## 10. Első fejlesztési mérföldkövek

### M1 — Követelmények és adatmodell

- Követelmények pontosítása.
- JSON-adatformátum megtervezése.
- Tesztadatok létrehozása.

### M2 — Optimalizálási modell

- Döntési változók meghatározása.
- Korlátozások formalizálása.
- Célfüggvény meghatározása.
- Optimalizáló könyvtár kiválasztása.

### M3 — Optimalizáló prototípus

- Bemeneti adatok beolvasása.
- Optimalizálás futtatása.
- Eredmény előállítása.
- Alapvető tesztek készítése.

### M4 — Backend

- Python alapú API létrehozása.
- Adatbetöltési végpontok.
- Optimalizálási végpont.
- Eredmény lekérdezése.

### M5 — Frontend

- Mérkőzések feltöltése.
- Optimalizálás indítása.
- Eredmény megjelenítése.
- Hibák és figyelmeztetések megjelenítése.

### M6 — Tesztelés és dokumentáció

- Tesztesetek készítése.
- Optimalizálási eredmények kiértékelése.
- Teljesítménymérés.
- Szakdolgozati dokumentáció elkészítése.