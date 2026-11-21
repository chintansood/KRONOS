"""Static reference data for the synthetic world: places, names, organisations.
Coordinates are approximate real-world centroids; all people/accounts are fictional."""

AGENCIES = {
    "AGY-CHD": "Chandigarh Police",
    "AGY-PB": "Punjab Police",
    "AGY-HR": "Haryana Police",
    "AGY-DL": "Delhi Police",
}

# city -> (district, agency, police stations)
CITIES = {
    "Chandigarh": ("Chandigarh", "AGY-CHD", ["PS Sector 17", "PS Sector 36", "PS Industrial Area", "PS Cyber Crime CHD"]),
    "Mohali":     ("SAS Nagar", "AGY-PB", ["PS Phase 8 Mohali", "PS Sohana", "PS Cyber Crime Mohali"]),
    "Ludhiana":   ("Ludhiana", "AGY-PB", ["PS Division No. 5", "PS Sarabha Nagar"]),
    "Amritsar":   ("Amritsar", "AGY-PB", ["PS Kotwali Amritsar"]),
    "Panchkula":  ("Panchkula", "AGY-HR", ["PS Sector 5 Panchkula"]),
    "Ambala":     ("Ambala", "AGY-HR", ["PS Ambala Cantt", "PS Ambala City"]),
    "Gurugram":   ("Gurugram", "AGY-HR", ["PS Cyber City", "PS Sector 56"]),
    "Delhi":      ("New Delhi", "AGY-DL", ["PS Karol Bagh", "PS Dwarka South", "PS Connaught Place", "PS IFSO Cyber Cell"]),
    "Mumbai":     ("Mumbai Suburban", None, []),
    "Jaipur":     ("Jaipur", None, []),
}

CASE_CITIES = ["Chandigarh", "Chandigarh", "Mohali", "Ludhiana", "Panchkula", "Ambala", "Gurugram", "Delhi", "Delhi", "Amritsar"]

# place_id, name, city, type, lat, lon
PLACES = [
    ("LOC-CHD-01", "Sector 17 Plaza, Chandigarh", "Chandigarh", "COMMERCIAL", 30.7410, 76.7790),
    ("LOC-CHD-02", "Sector 22 Market, Chandigarh", "Chandigarh", "MARKET", 30.7333, 76.7794),
    ("LOC-CHD-03", "Sector 35 Residential, Chandigarh", "Chandigarh", "RESIDENTIAL", 30.7225, 76.7570),
    ("LOC-CHD-04", "ISBT Sector 43, Chandigarh", "Chandigarh", "TRANSIT", 30.7190, 76.7480),
    ("LOC-CHD-05", "Elante Mall, Industrial Area Chandigarh", "Chandigarh", "COMMERCIAL", 30.7056, 76.8013),
    ("LOC-CHD-06", "Sector 9 Office Complex, Chandigarh", "Chandigarh", "OFFICE", 30.7480, 76.7900),
    ("LOC-CHD-07", "Sector 15 Residential, Chandigarh", "Chandigarh", "RESIDENTIAL", 30.7460, 76.7670),
    ("LOC-CHD-08", "Sector 26 Grain Market, Chandigarh", "Chandigarh", "MARKET", 30.7290, 76.8090),
    ("LOC-CHD-09", "Manimajra Housing Complex, Chandigarh", "Chandigarh", "RESIDENTIAL", 30.7170, 76.8350),
    ("LOC-CHD-10", "Chandigarh Railway Station", "Chandigarh", "TRANSIT", 30.7020, 76.8220),
    ("LOC-MOH-01", "Phase 7 Market, Mohali", "Mohali", "MARKET", 30.7100, 76.7200),
    ("LOC-MOH-02", "Phase 8 Industrial Area, Mohali", "Mohali", "OFFICE", 30.7080, 76.7040),
    ("LOC-MOH-03", "Sector 70 Residential, Mohali", "Mohali", "RESIDENTIAL", 30.6980, 76.7140),
    ("LOC-MOH-04", "Kharar Highway Dhaba, Mohali", "Mohali", "PUBLIC", 30.7450, 76.6450),
    ("LOC-MOH-05", "Airport Road, Mohali", "Mohali", "TRANSIT", 30.6650, 76.7600),
    ("LOC-PKL-01", "Sector 5 Market, Panchkula", "Panchkula", "MARKET", 30.6950, 76.8550),
    ("LOC-PKL-02", "Sector 20 Residential, Panchkula", "Panchkula", "RESIDENTIAL", 30.6700, 76.8650),
    ("LOC-AMB-01", "Sadar Bazaar, Ambala Cantt", "Ambala", "MARKET", 30.3340, 76.8380),
    ("LOC-AMB-02", "Ambala City Residential Colony", "Ambala", "RESIDENTIAL", 30.3780, 76.7760),
    ("LOC-AMB-03", "Ambala Cantt Railway Station", "Ambala", "TRANSIT", 30.3390, 76.8290),
    ("LOC-LDH-01", "Ghumar Mandi Market, Ludhiana", "Ludhiana", "MARKET", 30.9100, 75.8250),
    ("LOC-LDH-02", "Focal Point Industrial Area, Ludhiana", "Ludhiana", "OFFICE", 30.8890, 75.9300),
    ("LOC-LDH-03", "Sarabha Nagar Residential, Ludhiana", "Ludhiana", "RESIDENTIAL", 30.8850, 75.8150),
    ("LOC-ASR-01", "Hall Bazaar, Amritsar", "Amritsar", "MARKET", 31.6280, 74.8750),
    ("LOC-ASR-02", "Ranjit Avenue Residential, Amritsar", "Amritsar", "RESIDENTIAL", 31.6460, 74.8580),
    ("LOC-DEL-01", "Karol Bagh Market, Delhi", "Delhi", "MARKET", 28.6519, 77.1909),
    ("LOC-DEL-02", "Dwarka Sector 10 Residential, Delhi", "Delhi", "RESIDENTIAL", 28.5820, 77.0560),
    ("LOC-DEL-03", "Connaught Place Offices, Delhi", "Delhi", "OFFICE", 28.6315, 77.2167),
    ("LOC-DEL-04", "Chandni Chowk Market, Delhi", "Delhi", "MARKET", 28.6506, 77.2303),
    ("LOC-DEL-05", "IGI Airport Terminal 3, Delhi", "Delhi", "TRANSIT", 28.5562, 77.1000),
    ("LOC-DEL-06", "Laxmi Nagar Residential, Delhi", "Delhi", "RESIDENTIAL", 28.6304, 77.2777),
    ("LOC-GGN-01", "Cyber City Offices, Gurugram", "Gurugram", "OFFICE", 28.4950, 77.0890),
    ("LOC-GGN-02", "Sector 56 Residential, Gurugram", "Gurugram", "RESIDENTIAL", 28.4230, 77.1030),
    ("LOC-MUM-01", "Andheri East Offices, Mumbai", "Mumbai", "OFFICE", 19.1136, 72.8697),
    ("LOC-MUM-02", "Bandra West Residential, Mumbai", "Mumbai", "RESIDENTIAL", 19.0596, 72.8295),
    ("LOC-MUM-03", "Mumbai Airport Terminal 2", "Mumbai", "TRANSIT", 19.0974, 72.8745),
    ("LOC-JAI-01", "Johari Bazaar, Jaipur", "Jaipur", "MARKET", 26.9220, 75.8260),
]

MALE_FIRST = ["Amit", "Rahul", "Vikram", "Sandeep", "Rajesh", "Manoj", "Sunil", "Arjun", "Karan", "Harpreet",
              "Gurpreet", "Jaspreet", "Mohit", "Deepak", "Ravi", "Ankit", "Nitin", "Sanjay", "Varun", "Rohit",
              "Ajay", "Pankaj", "Naveen", "Sahil", "Yogesh", "Imran", "Farhan", "Tarun", "Lakhwinder", "Balwinder",
              "Kuldeep", "Manpreet", "Aman", "Abhishek", "Gaurav", "Vivek", "Ashok", "Dinesh", "Mukesh", "Sachin"]
FEMALE_FIRST = ["Priya", "Neha", "Pooja", "Simran", "Anjali", "Kavita", "Sunita", "Ritu", "Meena", "Navneet",
                "Harleen", "Jasleen", "Shalini", "Divya", "Nisha", "Rekha", "Komal", "Sakshi", "Aarti", "Manisha"]
SURNAMES = ["Sharma", "Verma", "Gupta", "Singh", "Kaur", "Gill", "Sandhu", "Sidhu", "Mehta", "Arora", "Bansal",
            "Malhotra", "Kapoor", "Chopra", "Yadav", "Chauhan", "Rana", "Saini", "Bhatia", "Khanna", "Grewal",
            "Dhillon", "Bajwa", "Kumar", "Jain", "Aggarwal", "Thakur", "Rawat", "Qureshi", "Khan"]

# (formal name, alias used in another case) – same underlying human
ALIAS_PAIRS = [
    ("Ram Kumar", "Raju"), ("Vikramjit Singh", "Vicky Singh"), ("Mohammed Irfan", "Irfan Bhai"),
    ("Sukhwinder Singh", "Sukha"), ("Rakesh Sharma", "Rocky Sharma"), ("Gurpreet Singh Dhillon", "Gopi Dhillon"),
    ("Santosh Yadav", "Santu Yadav"), ("Manoj Kumar Rana", "Monu Rana"), ("Harjinder Singh", "Harry Singh"),
    ("Devendra Pal", "Dev Pal"),
]
NICKNAMES = {  # canonical first name -> known nickname forms (used by identity resolution too)
    "ram": ["raju", "ramu"], "vikramjit": ["vicky", "vikram"], "vikram": ["vicky"], "mohammed": ["md", "mohd"],
    "sukhwinder": ["sukha", "sukhi"], "rakesh": ["rocky"], "gurpreet": ["gopi", "gopy"], "santosh": ["santu"],
    "manoj": ["monu"], "harjinder": ["harry"], "devendra": ["dev"], "rajesh": ["raju"], "rajinder": ["raju"],
    "harpreet": ["happy"], "jaspreet": ["jassi"], "kuldeep": ["kd"], "balwinder": ["billa"], "sandeep": ["sandy"],
}
NAMESAKES = ["Amit Sharma", "Rahul Verma", "Pooja Singh", "Sunil Kumar", "Neha Gupta", "Ravi Yadav", "Ajay Chauhan", "Simran Kaur"]

BANKS = [("SBIN", "State Bank of India"), ("HDFC", "HDFC Bank"), ("ICIC", "ICICI Bank"),
         ("PUNB", "Punjab National Bank"), ("UTIB", "Axis Bank"), ("KKBK", "Kotak Mahindra Bank")]

# org_id, name, kind, city
ORGS = [
    ("ORG-001", "Tricity Logistics Pvt Ltd", "EMPLOYER", "Chandigarh"),
    ("ORG-002", "Sunrise Textiles", "EMPLOYER", "Ludhiana"),
    ("ORG-003", "Punjab Agro Foods Ltd", "EMPLOYER", "Mohali"),
    ("ORG-004", "Northline IT Services", "EMPLOYER", "Gurugram"),
    ("ORG-005", "Capital Motors", "EMPLOYER", "Delhi"),
    ("ORG-006", "Greenfield Hospital", "EMPLOYER", "Chandigarh"),
    ("ORG-007", "Ambala Hardware Traders", "EMPLOYER", "Ambala"),
    ("ORG-008", "Delhi Garments Hub", "EMPLOYER", "Delhi"),
    ("ORG-009", "Shivalik Builders", "BUILDER", "Mohali"),
    ("ORG-010", "Smart Bazaar Retail", "MERCHANT", "Chandigarh"),
    ("ORG-011", "City Fuel Station", "MERCHANT", "Chandigarh"),
    ("ORG-012", "FoodRun Delivery", "MERCHANT", "Delhi"),
    ("ORG-013", "IRCTC Ticketing", "MERCHANT", "Delhi"),
    ("ORG-014", "SkyWings Airlines", "MERCHANT", "Delhi"),
    ("ORG-015", "PowerGrid Electricity Board", "MERCHANT", "Chandigarh"),
    ("ORG-016", "Nexgen Bullion Traders", "SHELL", "Ambala"),
    ("ORG-017", "Orbit Impex", "SHELL", "Delhi"),
    ("ORG-018", "Silverline Trading Co", "SHELL", "Ludhiana"),
    ("ORG-019", "Apex Global Exports", "SHELL", "Gurugram"),
    ("ORG-020", "Royal Jewellers", "MERCHANT", "Amritsar"),
    ("ORG-021", "QuickCash Fintech", "SHELL", "Mohali"),
    ("ORG-022", "Metro Pharmacy", "MERCHANT", "Delhi"),
]

INNOCENT_MESSAGES = [
    "Reached office, will call you at lunch.", "Please pick up vegetables on the way home.",
    "Mummy is asking when you will come for dinner.", "Meeting shifted to 4 pm, conference room B.",
    "Happy birthday! Party at home tonight.", "Did you pay the electricity bill?",
    "Traffic is very bad near {place}, will be late.", "Send me the photos from the wedding.",
    "Can you share the report by evening?", "Cricket match at 7, coming?",
    "Kids have parent teacher meeting tomorrow at 10.", "I am at {place}, need anything?",
    "Rent for this month sent, please confirm.", "Doctor appointment confirmed for Monday.",
    "Call me when free.", "Ok done.", "Thanks bhai!", "Reached home safely.",
]

# Scenario -> (offence category, sections, title templates)
SCENARIOS = {
    "INVESTMENT_FRAUD": ("Cyber Fraud (Online Investment Scam)", "BNS 318(4), 319; IT Act 66D",
                         ["Online Trading App Investment Scam", "Fake Crypto Returns Scheme", "Stock Tip Telegram Fraud"]),
    "SHELL_LAYERING":   ("Financial Fraud & Money Laundering", "BNS 316, 318, 61; PMLA 3",
                         ["Bullion Invoice Diversion via Shell Firms", "Fake Export Invoice Layering", "Trade-Based Fund Diversion"]),
    "EXTORTION":        ("Extortion & Criminal Intimidation", "BNS 308, 351",
                         ["Shopkeeper Extortion Racket", "Protection Money Demand", "Builder Extortion Calls"]),
    "NARCOTICS":        ("Narcotics Supply (NDPS)", "NDPS Act 21, 29",
                         ["Highway Narcotics Supply Chain", "Inter-district Contraband Network"]),
    "VEHICLE_THEFT":    ("Vehicle Theft", "BNS 303(2), 317",
                         ["Two-Wheeler Theft Ring", "SUV Theft and Resale"]),
    "FALSE_ACCUSATION": ("Cheating (Disputed Complaint)", "BNS 318",
                         ["Property Deal Cheating Complaint", "Business Partner Dispute Complaint"]),
}
SCENARIO_WEIGHTS = {"INVESTMENT_FRAUD": 0.24, "SHELL_LAYERING": 0.18, "EXTORTION": 0.16,
                    "NARCOTICS": 0.16, "VEHICLE_THEFT": 0.14, "FALSE_ACCUSATION": 0.12}

INVESTIGATORS = ["Insp. Arvind Rawat", "DSP Meenakshi Sharma", "SI Vikram Chopra", "Insp. Neelam Bajwa",
                 "ACP Rohit Malik", "SI Harjeet Kaur", "Insp. Sameer Qureshi", "DSP Anil Dhankar"]

# Fathers' first names (older generation) — used in FIR "particulars of accused" (S/o) and criminal records
FATHER_FIRST = ["Mohan Lal", "Ram Prakash", "Jagdish", "Baldev", "Surinder", "Harbhajan", "Om Prakash", "Krishan",
                "Satpal", "Gurdev", "Mahinder", "Darshan", "Rajinder", "Kewal", "Tarsem", "Hukam Chand", "Prem Nath",
                "Joginder", "Ramesh Chand", "Ishwar", "Bachan", "Nirmal", "Sohan Lal", "Amarjit", "Charan Das"]

# Prior-record templates for the criminal-history source: (offence, sections, modus operandi)
HISTORY_OFFENCES = [
    ("Theft", "IPC 379", "Lifted two-wheelers from market parking using duplicate keys"),
    ("Cheating", "IPC 420", "Collected advance payments for goods that were never delivered"),
    ("NDPS possession", "NDPS Act 22", "Carried small quantities of contraband in a private vehicle"),
    ("Extortion", "IPC 384", "Demanded money from shopkeepers by phone threats"),
    ("Online fraud", "IT Act 66D", "Posed as bank official on phone to obtain OTPs"),
    ("Criminal breach of trust", "IPC 406", "Misappropriated company cash collections"),
    ("Forgery", "IPC 467, 471", "Used forged invoices to obtain payments"),
    ("Assault", "IPC 323", "Altercation at a public place"),
]
MINOR_OFFENCES = [
    ("Cheque dishonour", "NI Act 138", "Cheque returned for insufficient funds in a business dispute"),
    ("Affray", "IPC 160", "Scuffle at a wedding function"),
    ("Rash driving", "IPC 279", "Road accident complaint"),
]
DISPOSITIONS = [("CONVICTED", 0.33), ("PENDING_TRIAL", 0.27), ("ACQUITTED", 0.22), ("DISCHARGED", 0.10), ("COMPOUNDED", 0.08)]
HISTORY_SOURCES = ["CCTNS (State Crime Records)", "District Crime Record Bureau", "Court case register"]
