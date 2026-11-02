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
    "saudi_arabia": ["Saudi Arabia", "KSA", "Riyadh", "Jeddah", "Dammam", "Dhahran", "Khobar", "Al Khobar",
                     "Thuwal", "KAUST", "NEOM", "Mecca", "Makkah", "Medina", "Madinah", "Jubail", "Yanbu",
                     "Abha", "Tabuk", "السعودية", "الرياض", "جدة"],
    "qatar": ["Qatar", "Doha", "Lusail", "Al Rayyan", "Ar-Rayyan", "Al Wakrah", "Education City", "Ras Laffan",
              "قطر", "الدوحة"],
    "kuwait": ["Kuwait", "Kuwait City", "Shuwaikh", "Hawalli", "Salmiya", "Ahmadi", "Jahra", "Farwaniya",
               "الكويت"],
    "uae": ["United Arab Emirates", "UAE", "U.A.E.", "Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Al Ain",
            "Ras Al Khaimah", "Fujairah", "Masdar City", "الإمارات", "دبي", "أبوظبي"],
    "bahrain": ["Bahrain", "Manama", "Muharraq", "Riffa", "Sakhir", "البحرين", "المنامة"],
    "oman": ["Oman", "Muscat", "Salalah", "Sohar", "Nizwa", "Muscat Governorate", "عمان", "مسقط"],
    "germany": ["Germany", "Deutschland", "Berlin", "Munich", "München", "Hamburg", "Frankfurt", "Cologne",
                "Köln", "Stuttgart", "Darmstadt", "Karlsruhe", "Bonn", "Potsdam", "Oberpfaffenhofen",
                "Weßling", "Wessling", "Neustrelitz", "Bremen", "Hannover", "Dresden", "Leipzig", "Heidelberg",
                "Freiburg", "Würzburg", "Immenstaad", "Friedrichshafen", "Ottobrunn", "Taufkirchen",
                "Düsseldorf", "Aachen", "Nuremberg", "Nürnberg", "Jena", "Mainz", "Eschborn", "Gilching"],
}
# Adzuna locations end with the country code we searched, e.g. "London (GB)"
CODES = {"GB": "uk", "FR": "france", "CH": "switzerland", "MA": "morocco", "JP": "japan",
         "SA": "saudi_arabia", "QA": "qatar", "KW": "kuwait", "AE": "uae", "BH": "bahrain", "OM": "oman",
         "DE": "germany"}
REMOTE_OPEN = re.compile(r"\b(worldwide|anywhere|global|europe|emea|africa|mena|gcc|middle east)\b", re.I)


def _has(text: str, word: str) -> bool:
    flags = 0 if word.isupper() else re.I  # "UK" must stay uppercase
    if any(ord(c) >= 0x0600 for c in word):
        return word in text  # Arabic / Japanese names: match as plain text
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
          "france": "France", "japan": "Japan", "saudi_arabia": "Saudi Arabia", "qatar": "Qatar",
          "kuwait": "Kuwait", "uae": "United Arab Emirates", "bahrain": "Bahrain", "oman": "Oman",
          "germany": "Germany", "remote": "Remote", "": "Unknown"}
