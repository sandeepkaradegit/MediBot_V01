# MediBot
MediAssist Health Network is a mid-sized private healthcare group operating across 12 hospitals and 40+ clinics in India. Internal knowledge (clinical treatment protocols, drug formularies, hospital policy handbooks, insurance billing guides, and equipment maintenance manuals) is scattered across hundreds of PDFs

## 1. Add Your Raw Data

Before running ingestion, place your source documents into the correct category folder under `raw_data/`:

```
raw_data/
├── db/                     # Structured/tabular data (e.g. exported DB tables, CSVs)
└── mediassist_data/
    ├── billing/            # Billing & insurance-related documents
    ├── clinical/           # Clinical notes, diagnoses, treatment records
    ├── equipment/          # Equipment manuals, maintenance/inventory docs
    ├── general/            # General hospital/policy documents that don't fit other categories
    └── nursing/            # Nursing protocols, care guidelines, shift notes
```

**Steps:**
1. Identify which category your document belongs to (billing, clinical, equipment, general, nursing, or db).
2. Copy the file into the matching subfolder under `raw_data/mediassist_data/` (or `raw_data/db/` for structured data).
3. Each subfolder has its own `readme.md` — check it for any category-specific notes before adding files.
4. Refer Readme.md respectively in MediBot-BackEnd and MediBot-FrontEnd folder resepctive to understand more about flow and running the application.

> ⚠️ Do not place files directly in `raw_data/` or `mediassist_data/` — they must go inside the correct category subfolder, or the ingestion step won't pick them up correctly.
