# Dashboard chart plan

Window: 2021 to 2025, matching the COBS and GMN pulls.
Globe at Night runs 2006 to 2024, so trim it to 2021 to 2024 for cross-source
charts, or use its full span only where the chart stands alone.

Each panel below gives the axes, the source, and the finding it should show.
Findings are the claim you expect to make. Replace any that the data contradicts.

---

## Section 01: Where the telescopes are

### 1.1 Observatory sites map
- **X / Y:** longitude and latitude, one point per site
- **Source:** MPC observatory codes (converted from parallax constants)
- **Finding:** amateur observatories cluster in Europe, North America and Japan, with large gaps across Africa, Central Asia and South America

### 1.2 Observatories per country
- **X-axis:** country, top 20
- **Y-axis:** number of registered observatory sites
- **Source:** MPC observatory codes, parsed from site names
- **Finding:** a handful of countries hold most of the world's registered amateur observatories

### 1.3 Active observers per country
- **X-axis:** country
- **Y-axis:** distinct observer codes, 2021 to 2025
- **Source:** COBS, derived table
- **Finding:** the countries that own the equipment are also the ones filing the observations, so access and contribution track each other

### 1.4 Telescope and binocular imports
- **X-axis:** year
- **Y-axis:** import value, selected countries
- **Source:** OEC / UN Comtrade, HS code 9005
- **Finding:** equipment flows into the same countries that dominate the observation record, which supports the ownership proxy

---

## Section 02: Observation records over time

### 2.1 Observations per year
- **X-axis:** year
- **Y-axis:** observation count, one line per archive
- **Source:** COBS and Globe at Night
- **Finding:** contribution volume is uneven year to year, driven by what appeared in the sky rather than by steady growth

### 2.2 Meteor trajectories per year
- **X-axis:** year
- **Y-axis:** trajectories recorded
- **Source:** GMN
- **Finding:** meteor records grow steeply every year, but the growth comes from new cameras joining rather than more meteors

### 2.3 Observations per observer
- **X-axis:** observers, ranked from most to least active
- **Y-axis:** observations filed
- **Source:** COBS, grouped by observer code
- **Finding:** a small core files most of the record while the majority contribute a handful of nights, so the archive rests on a few dozen people

### 2.4 Most observed comets
- **X-axis:** comet designation, top 10
- **Y-axis:** observations
- **Source:** COBS
- **Finding:** attention concentrates on a few bright comets, with a long tail of objects almost nobody watches

---

## Section 03: Celestial events compared

### 3.1 Daily observations with event markers
- **X-axis:** date, 2021 to 2025
- **Y-axis:** observations per day
- **Source:** COBS daily counts, with eclipse and perihelion dates marked from the NASA catalogue
- **Finding:** activity is flat most of the year and spikes sharply around a few events, then decays within weeks

### 3.2 Observation volume per event
- **X-axis:** events (C/2021 A1 Leonard, C/2022 E3 ZTF, the 2023 annular eclipse, the 2024 total eclipse, C/2023 A3 Tsuchinshan-ATLAS, Perseids peaks)
- **Y-axis:** observations in the 30 days around each event
- **Source:** COBS, with Globe at Night as a second series where the dates fall inside its coverage
- **Finding:** bright comets pull far more observing activity than any other event type, and the gap between the biggest and smallest event is large

### 3.3 Meteor shower activity
- **X-axis:** solar longitude (removes calendar drift between years)
- **Y-axis:** meteors recorded, one line per year
- **Source:** GMN, filtered by iau_code to PER, GEM, QUA
- **Finding:** shower peaks land in the same place every year, so meteor activity is predictable in a way comets are not

### 3.4 Fireballs per year
- **X-axis:** year
- **Y-axis:** recorded fireball events
- **Source:** NASA CNEOS
- **Finding:** fireballs arrive at a roughly steady rate, independent of whether anyone was watching

---

## Section 04: Community participation

### 4.1 Globe at Night participants per year
- **X-axis:** year, 2006 to 2024
- **Y-axis:** observations submitted
- **Source:** Globe at Night yearly CSVs
- **Finding:** casual participation peaked around 2020 and has declined since, unlike the equipment-heavy archives

### 4.2 Participation by country
- **X / Y:** world map, shaded by submissions per country
- **Source:** Globe at Night country column
- **Finding:** the casual audience is spread more widely than the equipped one, reaching countries with no registered observatories

### 4.3 Observers per association
- **X-axis:** observations
- **Y-axis:** association, ranked
- **Source:** COBS association field
- **Finding:** a few long-running societies supply a disproportionate share of the record, so organised clubs still matter

### 4.4 Active clubs and public events
- **X-axis:** US state
- **Y-axis:** active clubs, or events in the last six months
- **Source:** NASA Night Sky Network, tabulated by hand
- **Finding:** club activity concentrates in the same states that host the most observatories

---

## Section 05: Technology and accessibility

### 5.1 Visual versus CCD share per year
- **X-axis:** year
- **Y-axis:** share of observations, visual against CCD
- **Source:** COBS, derived method table
- **Finding:** the sensor share rises steadily, so skill at eyepiece estimation matters less than it used to

### 5.2 Aperture distribution over time
- **X-axis:** year
- **Y-axis:** instrument aperture in cm, distribution per year
- **Source:** COBS instrument aperture
- **Finding:** the typical aperture in use has not grown much, so improvement came from sensors rather than bigger telescopes

### 5.3 Instrument types
- **X-axis:** observations
- **Y-axis:** instrument type (Newtonian, refractor, binoculars, naked eye)
- **Source:** COBS instrument type, ICQ key lookup
- **Finding:** reflectors dominate, but low-cost options still account for a visible share of the record

### 5.4 Camera and chip types
- **X-axis:** year
- **Y-axis:** observations by chip family
- **Source:** COBS camera and chip type
- **Finding:** CMOS sensors displace CCDs over the period, tracking the wider consumer camera market

### 5.5 Meteor camera stations per year
- **X-axis:** year
- **Y-axis:** distinct station codes, optionally split by country
- **Source:** GMN participating_stations
- **Finding:** the camera network grows fast and spreads to new countries, which is the clearest evidence that cheap hardware widened access

### 5.6 Search interest against event dates
- **X-axis:** date
- **Y-axis:** relative search interest for "telescope" and "smart telescope"
- **Source:** Google Trends export
- **Finding:** public interest spikes with events rather than growing steadily, so events, not technology, drive attention

---

## Notes that apply across the dashboard

- Raw counts track observer and camera density as much as sky activity. Where
  growth could be explained by more participants, normalise (per observer,
  per station) and say so.
- NEOWISE 2020 and the 2017 eclipse sit outside the 2021 to 2025 window. Either
  widen the pull or leave them out rather than mixing windows.
- Each source is blind to events outside its domain. A flat COBS line during an
  eclipse is evidence about different audiences, not missing data.