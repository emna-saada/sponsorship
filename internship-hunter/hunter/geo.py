"""Which country an opportunity is in, from its location text."""
import re

COUNTRIES = {
    "switzerland": ["Switzerland", "Suisse", "Schweiz", "Svizzera", "Zurich", "Zürich", "Geneva", "Genève",
                    "Lausanne", "Bern", "Berne", "Basel", "Bâle", "Lugano", "Heerbrugg", "St. Gallen",
                    "Winterthur", "Zug", "Fribourg", "Neuchâtel", "Sion", "Yverdon", "Wabern", "Birmensdorf",
                    "Dübendorf", "Prilly"],
    "morocco": ["Morocco", "Maroc", "Casablanca", "Rabat", "Marrakech", "Marrakesh", "Tangier", "Tanger",
                "Fès", "Fes", "Fez", "Agadir", "Benguerir", "Ben Guerir", "Kenitra", "Kénitra", "Meknes",
                "Meknès", "Oujda", "Tetouan", "Tétouan", "El Jadida", "Mohammedia"],
    "uk": ["United Kingdom", "UK", "U.K.", "England", "Scotland", "Wales", "Northern Ireland", "London",
           "Edinburgh", "Manchester", "Cambridge", "Oxford", "Bristol", "Southampton", "Glasgow", "Leeds",
           "Harwell", "Nottingham", "Reading", "Belfast", "Birmingham", "Guildford", "Sheffield",
           "Newcastle", "Liverpool", "Exeter", "Aberdeen", "Cardiff", "Leicester", "Norwich"],
    "france": ["France", "Paris", "Toulouse", "Lyon", "Marseille", "Montpellier", "Bordeaux", "Nantes",
               "Grenoble", "Lille", "Rennes", "Strasbourg", "Sophia Antipolis", "Pessac", "Saint-Mandé",
               "Champs-sur-Marne", "Brest", "Nice", "Orléans", "Plouzané", "Ramonville", "Labège",
               "Île-de-France", "Ile-de-France", "Versailles", "Nancy", "Rouen", "Clermont-Ferrand", "Dijon",
               "Tours", "Angers", "Caen", "Metz", "Saclay", "Massy", "Palaiseau", "Boulogne-Billancourt"],
    "japan": ["Japan", "日本", "Tokyo", "東京", "Osaka", "Kyoto", "Yokohama", "Nagoya", "Tsukuba", "Sapporo",
              "Fukuoka", "Sendai", "Kobe", "Chiba", "Kawasaki", "Sagamihara", "Hiroshima", "Okinawa"],
}
# Adzuna locations end with the country code we searched, e.g. "London (GB)"
CODES = {"GB": "uk", "FR": "france", "CH": "switzerland", "MA": "morocco", "JP": "japan"}
REMOTE_OPEN = re.compile(r"\b(worldwide|anywhere|global|europe|emea|africa|mena)\b", re.I)


def _has(text: str, word: str) -> bool:
    flags = 0 if word.isupper() else re.I  # "UK" must stay uppercase
    if any(ord(c) >= 0x2E80 for c in word):
        return word in text  # 日本 / 東京 have no word boundaries
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text, flags) is not None


def country(location: str, description: str = "") -> str:
    """Country key, 'remote' for remote roles open broadly, or '' if unknown."""
    m = re.search(r"\(([A-Z]{2})\)\s*$", location or "")
    if m and m.group(1) in CODES:
        return CODES[m.group(1)]
    for key, words in COUNTRIES.items():
        if any(_has(location or "", w) for w in words):
            return key
    if re.search(r"\bremote\b", location or "", re.I) and REMOTE_OPEN.search(location or ""):
        return "remote"
    # last resort: an explicit country name in the description
    for key, words in COUNTRIES.items():
        if _has(description[:3000], words[0]) or _has(description[:3000], words[1]):
            return key
    return ""


LABELS = {"switzerland": "Switzerland", "morocco": "Morocco", "uk": "United Kingdom",
          "france": "France", "japan": "Japan", "remote": "Remote", "": "Unknown"}
