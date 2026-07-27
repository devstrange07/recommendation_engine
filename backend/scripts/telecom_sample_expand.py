"""Expansion SKUs for telecom sample catalogs beyond the 200-record base."""

from __future__ import annotations

from itertools import chain

ProductTuple = tuple[str, str, str, str, str, int]

CAT_PHONE = "Electronics/Smartphones"
CAT_FOLD = "Electronics/Foldables"
CAT_ACC = "Electronics/Accessories"


def _color_phone(
    model: str,
    color: str,
    storage: str,
    desc: str,
    feat: str,
    amount: int,
    category: str = CAT_PHONE,
) -> ProductTuple:
    name = f"{model} — {color} {storage}"
    plan = f"Street — {color} {storage}"
    full_desc = f"{desc} India retail SKU in {color} finish."
    return (name, category, full_desc, plan, feat, amount)


def _storage_phone(
    model: str,
    storage: str,
    desc: str,
    feat: str,
    amount: int,
    category: str = CAT_PHONE,
) -> ProductTuple:
    name = f"{model} {storage}"
    plan = f"Street — {storage}"
    return (name, category, desc, plan, feat, amount)


def _acc(
    name: str,
    desc: str,
    plan: str,
    feat: str,
    amount: int,
) -> ProductTuple:
    return (name, CAT_ACC, desc, plan, feat, amount)


def expand_color_variants() -> list[ProductTuple]:
    colors = ["Titanium Black", "Silver Shadow", "Ocean Blue", "Forest Green", "Coral Pink"]
    items: list[ProductTuple] = []

    flagships = [
        (
            "Samsung Galaxy S26 Ultra",
            "Samsung Galaxy S26 Ultra flagship with Snapdragon 8 Elite Gen 5 and 200MP camera.",
            "200MP camera; Snapdragon 8 Elite Gen 5; AMOLED; S Pen; 5G",
            [
                ("12GB + 256GB", 124999),
                ("12GB + 512GB", 144999),
            ],
        ),
        (
            "Samsung Galaxy S26 Plus",
            "Samsung Galaxy S26 Plus value flagship with large AMOLED and Galaxy AI.",
            "Large AMOLED; flagship chipset; Galaxy AI; 5G",
            [("12GB + 256GB", 94999), ("12GB + 512GB", 104999)],
        ),
        (
            "Samsung Galaxy S26",
            "Compact Samsung Galaxy S26 base flagship for pocketable 2026 Galaxy buyers.",
            "Compact flagship; AMOLED; Galaxy AI; 5G",
            [("8GB + 256GB", 79999), ("12GB + 512GB", 89999)],
        ),
        (
            "Apple iPhone 17 Pro",
            "Apple iPhone 17 Pro with pro camera system and Apple Intelligence.",
            "Pro camera; Apple Intelligence; ProMotion; Face ID; 5G",
            [("256GB", 134900), ("512GB", 154900)],
        ),
        (
            "Apple iPhone 17 Pro Max",
            "Apple iPhone 17 Pro Max with largest display and battery in the 17 line.",
            "Pro Max display; Pro camera; Apple Intelligence; 5G",
            [("256GB", 149900), ("512GB", 169900)],
        ),
        (
            "Apple iPhone 17",
            "Apple iPhone 17 base model for most iOS buyers in India 2026.",
            "iOS; Apple Intelligence; Face ID; 5G; MagSafe",
            [("128GB", 82900), ("256GB", 92900)],
        ),
        (
            "OnePlus 15",
            "OnePlus 15 flagship with OxygenOS and Hasselblad-tuned camera.",
            "Flagship chipset; OxygenOS; Hasselblad camera; fast charge; 5G",
            [("12GB + 256GB", 69999), ("16GB + 512GB", 76999)],
        ),
        (
            "Google Pixel 10 Pro",
            "Google Pixel 10 Pro with telephoto camera and Pixel AI.",
            "Pro camera; Tensor; Pixel AI; 7-yr updates; 5G",
            [("256GB", 102899), ("512GB", 114899)],
        ),
        (
            "Vivo X300 Pro",
            "Vivo X300 Pro camera flagship with Zeiss optics.",
            "Zeiss camera; flagship SoC; AMOLED; 5G",
            [("12GB + 256GB", 99999), ("16GB + 512GB", 109999)],
        ),
        (
            "Xiaomi 15 Ultra",
            "Xiaomi 15 Ultra with Leica Summilux optics and variable aperture.",
            "Leica Summilux; flagship SoC; HyperOS; 5G",
            [("16GB + 512GB", 109999), ("16GB + 1TB", 124999)],
        ),
        (
            "Nothing Phone (4a)",
            "Nothing Phone (4a) with Glyph design and Nothing OS.",
            "Nothing OS; Glyph design; AMOLED; 5G",
            [("8GB + 256GB", 37999), ("12GB + 512GB", 42999)],
        ),
        (
            "Motorola Edge 70",
            "Motorola Edge 70 mid-premium with near-stock Android.",
            "Near-stock Android; AMOLED; large battery; 5G",
            [("8GB + 256GB", 27999), ("12GB + 512GB", 31999)],
        ),
    ]

    for model, desc, feat, storages in flagships:
        for color in colors:
            for storage, amount in storages:
                items.append(_color_phone(model, color, storage, desc, feat, amount))

    mid_colors = ["Midnight Black", "Pearl White", "Aurora Purple", "Sunset Gold"]
    mid_models = [
        (
            "Samsung Galaxy A56 5G",
            "Samsung Galaxy A56 5G premium A-series with Galaxy AI.",
            "AMOLED; Galaxy AI; multi-year updates; 5G",
            [("8GB + 128GB", 35999), ("8GB + 256GB", 38999)],
        ),
        (
            "Vivo V70",
            "Vivo V70 premium mid-ranger with strong selfie camera.",
            "Selfie camera; AMOLED; fast charge; 5G",
            [("8GB + 256GB", 39999), ("12GB + 512GB", 44999)],
        ),
        (
            "OnePlus Nord 6",
            "OnePlus Nord 6 with massive battery and OxygenOS.",
            "~9000mAh battery; OxygenOS; fast charging; 5G",
            [("8GB + 256GB", 44999), ("12GB + 512GB", 49999)],
        ),
        (
            "Redmi Note 15 Pro 5G",
            "Redmi Note 15 Pro 5G volume mid-ranger with AMOLED.",
            "AMOLED; large battery; HyperOS; 5G",
            [("8GB + 256GB", 24999), ("12GB + 512GB", 27999)],
        ),
        (
            "OPPO Reno14 Pro",
            "OPPO Reno14 Pro with portrait camera and ColorOS.",
            "Portrait camera; AMOLED; ColorOS; 5G",
            [("12GB + 256GB", 44999)],
        ),
        (
            "Realme 15 Pro 5G",
            "Realme 15 Pro 5G mid-ranger with fast charging.",
            "AMOLED; fast charge; mid SoC; 5G",
            [("8GB + 256GB", 27999)],
        ),
        (
            "POCO F7 Pro",
            "POCO F7 Pro with near-flagship Snapdragon performance.",
            "Near-flagship SoC; AMOLED; HyperOS; 5G",
            [("12GB + 256GB", 42999), ("16GB + 512GB", 47999)],
        ),
        (
            "iQOO 13",
            "iQOO 13 gaming flagship with advanced cooling.",
            "Flagship Snapdragon; gaming cooling; high refresh AMOLED; 5G",
            [("12GB + 256GB", 54999), ("16GB + 512GB", 59999)],
        ),
    ]

    for model, desc, feat, storages in mid_models:
        for color in mid_colors:
            for storage, amount in storages:
                items.append(_color_phone(model, color, storage, desc, feat, amount))

    return items


def expand_foldable_extras() -> list[ProductTuple]:
    """Limited foldable color SKUs to reach ~30 foldables in the 500 catalog."""
    items: list[ProductTuple] = []
    extras = [
        (
            "Samsung Galaxy Z Fold7",
            "Phantom Black",
            "12GB + 256GB",
            "Samsung Galaxy Z Fold7 book foldable in Phantom Black.",
            "Book foldable; S Pen; Galaxy AI; 5G",
            164999,
        ),
        (
            "Samsung Galaxy Z Fold7",
            "Silver Shadow",
            "12GB + 512GB",
            "Samsung Galaxy Z Fold7 Silver Shadow higher storage SKU.",
            "512GB; book foldable; S Pen; 5G",
            179999,
        ),
        (
            "Samsung Galaxy Z Flip7",
            "Mint",
            "8GB + 256GB",
            "Samsung Galaxy Z Flip7 clamshell in Mint finish.",
            "Clamshell foldable; cover screen; Galaxy AI; 5G",
            109999,
        ),
        (
            "Samsung Galaxy Z Flip7",
            "Lavender",
            "12GB + 512GB",
            "Samsung Galaxy Z Flip7 Lavender 512GB SKU.",
            "512GB; clamshell foldable; cover screen; 5G",
            119999,
        ),
        (
            "Google Pixel 10 Pro Fold",
            "Obsidian",
            "16GB + 256GB",
            "Google Pixel 10 Pro Fold Obsidian book foldable.",
            "Book foldable; Pixel camera; Tensor; 5G",
            159785,
        ),
        (
            "Google Pixel 10 Pro Fold",
            "Porcelain",
            "16GB + 512GB",
            "Google Pixel 10 Pro Fold Porcelain 512GB.",
            "512GB; book foldable; Pixel camera; 5G",
            174785,
        ),
        (
            "Motorola Razr 60 Ultra",
            "Midnight Blue",
            "12GB + 512GB",
            "Motorola Razr 60 Ultra clamshell in Midnight Blue.",
            "Clamshell foldable; large outer display; 5G",
            119999,
        ),
        (
            "Honor Magic V5",
            "Black",
            "16GB + 512GB",
            "Honor Magic V5 thin book foldable in Black.",
            "Book foldable; thin design; MagicOS; 5G",
            149999,
        ),
        (
            "OnePlus Open 2",
            "Emerald Dusk",
            "16GB + 512GB",
            "OnePlus Open 2 book foldable Emerald Dusk colorway.",
            "Book foldable; OxygenOS; Hasselblad; 5G",
            139999,
        ),
        (
            "Samsung Galaxy Z Flip6",
            "Yellow",
            "8GB + 256GB",
            "Samsung Galaxy Z Flip6 Yellow prior-gen Flip color SKU.",
            "Clamshell foldable; FlexWindow; Galaxy AI; 5G",
            84999,
        ),
        (
            "OPPO Find N5 Flip",
            "Rose Gold",
            "12GB + 512GB",
            "OPPO Find N5 Flip clamshell foldable Rose Gold India launch SKU.",
            "Clamshell foldable; Hasselblad; ColorOS; 5G",
            99999,
        ),
    ]
    for model, color, storage, desc, feat, amount in extras:
        items.append(_color_phone(model, color, storage, desc, feat, amount, category=CAT_FOLD))
    return items


def expand_storage_skus() -> list[ProductTuple]:
    items: list[ProductTuple] = []
    storage_lines = [
        ("Vivo Y400 5G", "8GB + 128GB", "Vivo Y400 5G budget 5G volume driver.", "5G; large battery; dual camera", 16999),
        ("Vivo Y400 5G", "8GB + 256GB", "Vivo Y400 5G 256GB storage variant.", "256GB; 5G; large battery", 18999),
        ("Vivo Y31 5G", "6GB + 128GB", "Vivo Y31 5G entry 5G handset.", "5G; large battery; dual camera", 14999),
        ("Vivo Y31 Pro 5G", "8GB + 128GB", "Vivo Y31 Pro 5G upspecced Y31.", "5G; better display; large battery", 16999),
        ("Vivo T4 5G", "8GB + 128GB", "Vivo T4 5G performance T-series.", "5G; high refresh; large battery", 21999),
        ("Vivo T4 5G", "8GB + 256GB", "Vivo T4 5G 256GB variant.", "256GB; high refresh; 5G", 23999),
        ("OPPO A6x 5G", "6GB + 128GB", "OPPO A6x 5G volume budget 5G.", "5G; large battery; ColorOS", 16999),
        ("OPPO A6x 5G", "8GB + 256GB", "OPPO A6x 5G 256GB.", "256GB; 5G; ColorOS", 18999),
        ("OPPO K14 5G", "8GB + 128GB", "OPPO K14 5G performance K-series.", "5G; high refresh; ColorOS", 22999),
        ("OPPO K14 5G", "8GB + 256GB", "OPPO K14 5G 256GB.", "256GB; high refresh; 5G", 24999),
        ("Redmi Note 15 5G", "6GB + 128GB", "Redmi Note 15 5G base Note.", "5G; large battery; HyperOS", 17999),
        ("Redmi Note 15 5G", "8GB + 256GB", "Redmi Note 15 5G 256GB.", "256GB; 5G; HyperOS", 19999),
        ("Redmi 15 5G", "6GB + 128GB", "Redmi 15 5G entry 5G Redmi.", "5G; large battery; HyperOS", 12999),
        ("Redmi 15 5G", "8GB + 256GB", "Redmi 15 5G 256GB.", "256GB; 5G; HyperOS", 14999),
        ("POCO M7 Pro 5G", "6GB + 128GB", "POCO M7 Pro 5G budget POCO.", "5G; high refresh; HyperOS", 14999),
        ("POCO M7 Pro 5G", "8GB + 256GB", "POCO M7 Pro 5G 256GB.", "256GB; 5G; HyperOS", 16999),
        ("Samsung Galaxy A36 5G", "8GB + 128GB", "Samsung Galaxy A36 5G mid A-series.", "AMOLED; Galaxy AI lite; 5G", 26999),
        ("Samsung Galaxy A36 5G", "8GB + 256GB", "Samsung Galaxy A36 5G 256GB.", "256GB; AMOLED; 5G", 29999),
        ("Samsung Galaxy A17 5G", "6GB + 128GB", "Samsung Galaxy A17 5G volume A-series.", "5G; large battery; One UI", 18999),
        ("Samsung Galaxy A17 5G", "8GB + 256GB", "Samsung Galaxy A17 5G 256GB.", "256GB; 5G; One UI", 20999),
        ("Samsung Galaxy M36 5G", "8GB + 128GB", "Samsung Galaxy M36 5G mid M-series.", "5G; AMOLED; One UI", 19999),
        ("Samsung Galaxy M36 5G", "8GB + 256GB", "Samsung Galaxy M36 5G 256GB.", "256GB; AMOLED; 5G", 21999),
        ("Realme 15 5G", "6GB + 128GB", "Realme 15 5G base.", "5G; large battery; Realme UI", 16999),
        ("Realme Narzo 80 Pro 5G", "6GB + 128GB", "Realme Narzo 80 Pro 5G value gaming.", "5G; high refresh; large battery", 19999),
        ("Moto G96 5G", "6GB + 128GB", "Moto G96 5G base G-series.", "5G; large battery; near-stock Android", 16999),
        ("OnePlus Nord CE 6 Lite 5G", "6GB + 128GB", "OnePlus Nord CE 6 Lite 128GB.", "5G; OxygenOS; large battery", 17999),
    ]
    for model, storage, desc, feat, amount in storage_lines:
        items.append(_storage_phone(model, storage, desc, feat, amount))
    return items


def expand_extended_brands() -> list[ProductTuple]:
    return [
        _storage_phone(
            "Nokia G42 5G", "8GB + 256GB",
            "Nokia G42 5G — durable mid-ranger with clean Android and long update promise.",
            "5G; stock Android; large battery; dual camera", 18999,
        ),
        _storage_phone(
            "Nokia C32 4G", "4GB + 128GB",
            "Nokia C32 4G — ultra-budget 4G Nokia for value buyers skipping 5G premiums.",
            "Large battery; dual camera; stock Android", 8999,
        ),
        _storage_phone(
            "Sony Xperia 1 VII", "12GB + 256GB",
            "Sony Xperia 1 VII — creator-focused flagship with 4K OLED and pro video tools.",
            "4K OLED; pro video; flagship SoC; 5G", 119999,
        ),
        _storage_phone(
            "Sony Xperia 10 VII", "8GB + 256GB",
            "Sony Xperia 10 VII — compact Xperia with clean Android and good audio.",
            "Compact; stereo speakers; AMOLED; 5G", 49999,
        ),
        _storage_phone(
            "itel P55 Plus 5G", "8GB + 256GB",
            "itel P55 Plus 5G — Transsion value 5G for sub-₹15k segment.",
            "5G; large battery; dual camera", 12999,
        ),
        _storage_phone(
            "itel A70 4G", "4GB + 128GB",
            "itel A70 4G — entry itel for first smartphone buyers.",
            "Large battery; dual camera; value pricing", 7499,
        ),
        _storage_phone(
            "Lava Blaze 3 5G", "6GB + 128GB",
            "Lava Blaze 3 5G — Made-in-India 5G with clean UI.",
            "5G; Made in India; large battery", 11999,
        ),
        _storage_phone(
            "Lava Agni 3 5G", "8GB + 256GB",
            "Lava Agni 3 5G — premium Lava with curved AMOLED.",
            "Curved AMOLED; 5G; Made in India", 24999,
        ),
        _storage_phone(
            "Micromax IN Note 3", "8GB + 256GB",
            "Micromax IN Note 3 — Indian brand mid-ranger with stock-like experience.",
            "AMOLED; 5G; large battery; Made in India", 16999,
        ),
        _storage_phone(
            "Micromax IN 2b", "4GB + 64GB",
            "Micromax IN 2b — entry Micromax for ultra-budget buyers.",
            "Large battery; dual camera; value pricing", 7499,
        ),
        _storage_phone(
            "JioPhone Next 2", "4GB + 64GB",
            "JioPhone Next 2 — affordable Android for Jio ecosystem users upgrading from feature phones.",
            "Android Go; 4G; Jio apps; value pricing", 6499,
        ),
        _storage_phone(
            "JioPhone Prima 4G", "2GB + 32GB",
            "JioPhone Prima 4G — smart feature phone style device for basic apps and UPI.",
            "4G; KaiOS/Android hybrid; Jio services", 4499,
        ),
        _storage_phone(
            "Nokia XR21 5G", "8GB + 128GB",
            "Nokia XR21 5G — rugged Nokia with IP69 and MIL-STD durability.",
            "Rugged; IP69; 5G; stock Android", 24999,
        ),
        _storage_phone(
            "Sony Xperia 5 VII", "12GB + 256GB",
            "Sony Xperia 5 VII — compact pro Xperia for one-hand use and video.",
            "Compact pro; 4K display; flagship SoC; 5G", 99999,
        ),
        _storage_phone(
            "Infinix GT 30 Pro 5G", "12GB + 256GB",
            "Infinix GT 30 Pro 5G — gaming-leaning Infinix with high refresh display.",
            "Gaming; high refresh; fast charge; 5G", 27999,
        ),
        _storage_phone(
            "Tecno Pova 7 Pro 5G", "8GB + 256GB",
            "Tecno Pova 7 Pro 5G — battery-focused Tecno for gaming and media.",
            "Huge battery; gaming; AMOLED; 5G", 22999,
        ),
        _storage_phone(
            "itel S24 Plus 5G", "8GB + 256GB",
            "itel S24 Plus 5G — stylish budget itel with AMOLED.",
            "AMOLED; 5G; dual camera; value pricing", 14999,
        ),
        _storage_phone(
            "Lava Yuva 5G Pro", "6GB + 128GB",
            "Lava Yuva 5G Pro — youth-focused Lava 5G with trendy design.",
            "5G; trendy design; large battery; Made in India", 13499,
        ),
        _storage_phone(
            "Nokia G21 4G", "6GB + 128GB",
            "Nokia G21 4G — prior Nokia G-series still stocked at clearance pricing.",
            "Large battery; stock Android; dual camera", 11999,
        ),
        _storage_phone(
            "Micromax Canvas Fire 6", "4GB + 128GB",
            "Micromax Canvas Fire 6 — dual-front-camera niche Micromax for selfie buyers.",
            "Dual selfie; 4G; large battery", 9999,
        ),
    ]


def expand_prior_gen() -> list[ProductTuple]:
    return [
        _storage_phone(
            "Apple iPhone 14 128GB", "128GB",
            "Apple iPhone 14 128GB — older iPhone at deep clearance after iPhone 17 cycle.",
            "Lightning/USB-C era; dual camera; Face ID; 5G", 49900,
        ),
        _storage_phone(
            "Apple iPhone 14 Plus 128GB", "128GB",
            "Apple iPhone 14 Plus clearance large-screen iPhone.",
            "Large display; dual camera; Face ID; 5G", 54900,
        ),
        _storage_phone(
            "Apple iPhone 15 Pro 128GB", "128GB",
            "Apple iPhone 15 Pro 128GB — prior Pro at reduced street pricing.",
            "Pro camera; titanium; Action Button; 5G", 99900,
        ),
        _storage_phone(
            "Samsung Galaxy S24 Ultra 12GB + 256GB", "12GB + 256GB",
            "Samsung Galaxy S24 Ultra prior Ultra still on sale below S26 pricing.",
            "200MP; S Pen; AMOLED; 5G", 89999,
        ),
        _storage_phone(
            "Samsung Galaxy S25 8GB + 256GB", "8GB + 256GB",
            "Samsung Galaxy S25 — one-generation-old compact flagship at discount.",
            "Compact flagship; AMOLED; Galaxy AI; 5G", 64999,
        ),
        _storage_phone(
            "Google Pixel 8 Pro 128GB", "128GB",
            "Google Pixel 8 Pro clearance — still strong camera for budget Pixel buyers.",
            "Pro camera; Tensor; Pixel AI; 5G", 54999,
        ),
        _storage_phone(
            "Google Pixel 9 128GB", "128GB",
            "Google Pixel 9 base prior-gen at reduced street prices.",
            "Pixel camera; Tensor; clean Android; 5G", 49999,
        ),
        _storage_phone(
            "OnePlus 12 12GB + 256GB", "12GB + 256GB",
            "OnePlus 12 prior flagship at clearance after OnePlus 15 launch.",
            "Flagship SoC; Hasselblad; OxygenOS; 5G", 44999,
        ),
        _storage_phone(
            "OnePlus Open", "16GB + 512GB",
            "OnePlus Open first-gen book foldable at reduced pricing after Open 2 launch.",
            "Book foldable; OxygenOS; Hasselblad; 5G", 119999, CAT_FOLD,
        ),
        _storage_phone(
            "Samsung Galaxy Z Fold6 12GB + 256GB", "12GB + 256GB",
            "Samsung Galaxy Z Fold6 prior Fold clearance.",
            "Book foldable; S Pen; Galaxy AI; 5G", 134999, CAT_FOLD,
        ),
        _storage_phone(
            "Samsung Galaxy Z Flip5 8GB + 256GB", "8GB + 256GB",
            "Samsung Galaxy Z Flip5 prior Flip at discounted street prices.",
            "Clamshell foldable; FlexWindow; 5G", 69999, CAT_FOLD,
        ),
        _storage_phone(
            "Vivo X100 Pro 12GB + 256GB", "12GB + 256GB",
            "Vivo X100 Pro prior camera flagship at clearance.",
            "Zeiss camera; flagship SoC; AMOLED; 5G", 64999,
        ),
        _storage_phone(
            "Xiaomi 14T 8GB + 256GB", "8GB + 256GB",
            "Xiaomi 14T prior T-series at discounted pricing.",
            "Leica camera; Dimensity; HyperOS; 5G", 34999,
        ),
        _storage_phone(
            "Realme GT 6 12GB + 256GB", "12GB + 256GB",
            "Realme GT 6 prior GT at clearance after GT 7 series.",
            "Near-flagship SoC; AMOLED; fast charge; 5G", 32999,
        ),
        _storage_phone(
            "OPPO Find N3 Flip 8GB + 256GB", "8GB + 256GB",
            "OPPO Find N3 Flip clamshell foldable at reduced street prices.",
            "Clamshell foldable; Hasselblad; ColorOS; 5G", 74999, CAT_FOLD,
        ),
        _storage_phone(
            "Honor Magic V3 12GB + 512GB", "12GB + 512GB",
            "Honor Magic V3 prior thin foldable at clearance.",
            "Book foldable; thin; MagicOS; 5G", 109999, CAT_FOLD,
        ),
        _storage_phone(
            "Motorola Razr 50 Ultra 12GB + 512GB", "12GB + 512GB",
            "Motorola Razr 50 Ultra prior clamshell at discount.",
            "Clamshell foldable; large cover display; 5G", 89999, CAT_FOLD,
        ),
        _storage_phone(
            "Google Pixel Fold 256GB", "256GB",
            "Google Pixel Fold first-gen at deep discount after Pixel 10 Pro Fold.",
            "Book foldable; Pixel camera; Tensor; 5G", 89999, CAT_FOLD,
        ),
        _storage_phone(
            "Apple iPhone SE (2024) 128GB", "128GB",
            "Apple iPhone SE (2024) — compact Touch ID iPhone for buyers avoiding large phones.",
            "Touch ID; compact; A-series chip; 5G", 42900,
        ),
        _storage_phone(
            "Samsung Galaxy S23 FE 8GB + 256GB", "8GB + 256GB",
            "Samsung Galaxy S23 FE older Fan Edition still popular under ₹40k.",
            "Exynos/Snapdragon FE; AMOLED; Galaxy AI; 5G", 34999,
        ),
    ]


def expand_extra_phones() -> list[ProductTuple]:
    """Additional unique SKUs to ensure enough phone expansions."""
    extras = [
        _storage_phone("Vivo Y300 5G", "8GB + 256GB", "Vivo Y300 5G new Y-series volume SKU.", "5G; large battery; dual camera", 15999),
        _storage_phone("Vivo Y200e 5G", "8GB + 128GB", "Vivo Y200e 5G affordable Y-series.", "5G; AMOLED; large battery", 17999),
        _storage_phone("OPPO A79 5G", "8GB + 256GB", "OPPO A79 5G mid A-series.", "5G; AMOLED; ColorOS", 19999),
        _storage_phone("OPPO A58 4G", "6GB + 128GB", "OPPO A58 4G value 4G for budget buyers.", "Large battery; ColorOS; dual camera", 11999),
        _storage_phone("Redmi 13C 5G", "4GB + 128GB", "Redmi 13C 5G entry Redmi 5G.", "5G; large battery; HyperOS", 10999),
        _storage_phone("Redmi 14C 4G", "4GB + 128GB", "Redmi 14C 4G ultra-budget Redmi.", "Large battery; HyperOS; value", 8999),
        _storage_phone("POCO X7 5G", "8GB + 256GB", "POCO X7 5G mid POCO with high refresh.", "High refresh; 5G; HyperOS", 25999),
        _storage_phone("POCO C75 5G", "6GB + 128GB", "POCO C75 5G step-up from C75 base.", "5G; large battery; HyperOS", 11999),
        _storage_phone("Realme C67 5G", "6GB + 128GB", "Realme C67 5G budget Realme.", "5G; large battery; Realme UI", 12999),
        _storage_phone("Realme Narzo 70x 5G", "6GB + 128GB", "Realme Narzo 70x 5G gaming value.", "5G; high refresh; large battery", 13999),
        _storage_phone("Samsung Galaxy F36 5G", "8GB + 128GB", "Samsung Galaxy F36 5G Flipkart F-series.", "5G; AMOLED; One UI", 20999),
        _storage_phone("Samsung Galaxy M56 5G", "8GB + 256GB", "Samsung Galaxy M56 5G premium M-series online.", "5G; AMOLED; large battery; One UI", 27999),
        _storage_phone("Samsung Galaxy A26 5G", "8GB + 256GB", "Samsung Galaxy A26 5G higher storage A26.", "256GB; IP65; AMOLED; 5G", 24999),
        _storage_phone("Moto G85 5G", "8GB + 256GB", "Moto G85 5G curved pOLED mid G-series.", "Curved pOLED; 5G; near-stock Android", 19999),
        _storage_phone("Moto G54 5G", "8GB + 256GB", "Moto G54 5G prior G-series clearance.", "5G; large battery; near-stock Android", 14999),
        _storage_phone("Honor 200 Pro", "12GB + 512GB", "Honor 200 Pro prior mid-premium Honor.", "Portrait camera; curved AMOLED; 5G", 39999),
        _storage_phone("Honor X9c 5G", "8GB + 256GB", "Honor X9c 5G durable mid-ranger.", "Durable build; 5G; large battery", 19999),
        _storage_phone("Asus Zenfone 12", "12GB + 256GB", "Asus Zenfone 12 compact flagship alternative to ROG.", "Compact flagship; AMOLED; 5G", 62999),
        _storage_phone("Asus ROG Phone 8 Pro", "16GB + 512GB", "Asus ROG Phone 8 Pro prior ROG at discount.", "AirTriggers; gaming; flagship SoC; 5G", 64999),
        _storage_phone("CMF Phone 2 Pro", "8GB + 256GB", "CMF Phone 2 Pro prior CMF at clearance.", "Modular; Nothing OS lite; 5G", 13999),
    ]
    return extras


def expand_accessory_cases() -> list[ProductTuple]:
    cases = [
        ("Samsung Galaxy S26 Ultra", "Spigen Ultra Hybrid", 2999),
        ("Samsung Galaxy S26 Ultra", "Spigen Tough Armor", 3299),
        ("Samsung Galaxy S26", "Samsung Silicone Case", 2499),
        ("Apple iPhone 17 Pro", "Apple FineWoven Case with MagSafe", 5900),
        ("Apple iPhone 17 Pro", "Spigen Ultra Hybrid MagFit", 2799),
        ("Apple iPhone 17", "Apple Clear Case with MagSafe", 4900),
        ("Google Pixel 10 Pro", "Google Pixel 10 Pro Case", 3499),
        ("Google Pixel 10 Pro", "Spigen Liquid Crystal", 1999),
        ("OnePlus 15", "OnePlus Kevlar Case", 2499),
        ("OnePlus Nord 6", "Nillkin Frosted Shield", 1299),
        ("Nothing Phone (4a)", "Nothing Case (4a)", 1999),
        ("Vivo V70", "Vivo V70 Silicone Case", 999),
        ("Redmi Note 15 Pro 5G", "Mi Note 15 Pro Rugged Case", 899),
        ("OPPO Reno14 Pro", "OPPO Reno14 Pro Flip Cover", 1499),
        ("Motorola Edge 70", "Motorola Edge 70 Fabric Case", 1299),
        ("Samsung Galaxy Z Fold7", "Samsung Z Fold7 Aramid Case", 4999),
        ("Samsung Galaxy Z Flip7", "Samsung Z Flip7 Silicone Ring Case", 3499),
        ("Apple iPhone 17 Pro Max", "ESR HaloLock Case", 2499),
        ("POCO F7 Pro", "POCO F7 Pro Hard Case", 799),
        ("Realme 15 Pro 5G", "Realme 15 Pro Clear Case", 699),
    ]
    items: list[ProductTuple] = []
    for phone, brand_case, amount in cases:
        name = f"{brand_case} for {phone}"
        desc = f"{brand_case} protective case for {phone} — India retail accessory SKU."
        plan = f"Street — {brand_case.split()[0]} Case"
        feat = f"Drop protection; precise cutouts; {phone} fit"
        items.append(_acc(name, desc, plan, feat, amount))
    return items


def expand_accessory_screen_glass() -> list[ProductTuple]:
    glass = [
        ("iPhone 17 Pro Max", "Belkin ScreenForce UltraGlass 2", 2999),
        ("iPhone 17", "ESR Tempered Glass 3-pack", 1299),
        ("Samsung Galaxy S26 Ultra", "Whitestone Dome Glass EZ", 4499),
        ("Samsung Galaxy A56 5G", "Nillkin CP+ Pro Glass", 699),
        ("Google Pixel 10", "Google Pixel 10 Screen Protector", 1499),
        ("OnePlus 15", "OnePlus Official Screen Protector", 999),
        ("Vivo V70", "Vivo V70 Tempered Glass", 499),
        ("Redmi Note 15 Pro 5G", "Redmi Note 15 Pro Glass 2-pack", 399),
        ("Samsung Galaxy Z Flip7", "Samsung Z Flip7 Inner+Outer Film Kit", 2499),
        ("Motorola Edge 70", "Motorola Edge 70 Glass", 599),
    ]
    items: list[ProductTuple] = []
    for phone, product, amount in glass:
        name = f"{product} for {phone}"
        desc = f"{product} tempered glass / film kit for {phone}."
        plan = f"Street — Glass for {phone.split()[0]}"
        feat = f"9H tempered; oleophobic; {phone} fit"
        items.append(_acc(name, desc, plan, feat, amount))
    return items


def expand_accessory_audio_charging() -> list[ProductTuple]:
    return [
        _acc("Realme Buds Air 7 Pro", "Realme Buds Air 7 Pro ANC earbuds for Realme/Oppo ecosystem.", "Street — Buds Air 7 Pro", "ANC; LDAC; fast charge case; USB-C", 3999),
        _acc("boAt Airdopes 181 Pro", "boAt Airdocs 181 Pro popular India TWS with ENx calling.", "Street — Airdopes 181 Pro", "ANC; ENx; ASAP charge; Bluetooth 5.3", 1999),
        _acc("Noise Buds VS104 Pro", "Noise Buds VS104 Pro value ANC earbuds.", "Street — VS104 Pro", "ANC; long battery; USB-C", 1499),
        _acc("JBL Tune Beam 2", "JBL Tune Beam 2 ANC earbuds with JBL signature sound.", "Street — Tune Beam 2", "ANC; JBL sound; IP54; USB-C", 6999),
        _acc("Samsung 25W USB-C Fast Charger", "Samsung 25W USB-C fast charger for Galaxy A/M/S series.", "Street — 25W USB-C", "25W PD; USB-C; Samsung certified", 1499),
        _acc("Apple MagSafe Charger", "Apple MagSafe wireless charger for iPhone MagSafe phones.", "Street — MagSafe Charger", "MagSafe 15W; USB-C; Apple certified", 4500),
        _acc("Anker 511 Nano Pro 30W", "Anker Nano Pro 30W GaN charger for travel.", "Street — Nano Pro 30W", "30W GaN; foldable; PD/PPS", 2499),
        _acc("Belkin BoostCharge Pro 3-in-1 MagSafe", "Belkin 3-in-1 MagSafe stand for iPhone, Watch, AirPods.", "Street — BoostCharge Pro 3-in-1", "MagSafe; 15W; Apple Watch; AirPods", 14999),
        _acc("Mi 33W SonicCharge Power Bank 20000mAh", "Xiaomi 33W 20000mAh power bank for Redmi/POCO users.", "Street — Mi 33W 20k", "20000mAh; 33W; dual port", 2199),
        _acc("Ambrane 30000mAh 65W Power Bank", "Ambrane 30000mAh 65W laptop-capable power bank.", "Street — 30k 65W", "30000mAh; 65W PD; triple port", 4999),
        _acc("Portronics Power Bank 10000mAh 22.5W", "Portronics slim 10000mAh power bank for daily carry.", "Street — Portronics 10k", "10000mAh; 22.5W; slim", 999),
        _acc("Apple Watch Sport Band 45mm — Ocean Band", "Apple Watch ocean band for Series 11 / Ultra swim use.", "Street — Ocean Band 45mm", "Ocean band; swimproof; 45mm fit", 9900),
        _acc("Samsung Galaxy Watch7 Sport Band", "Samsung official sport band for Galaxy Watch7.", "Street — Watch7 Sport Band", "Official Samsung; sport; Watch7 fit", 2999),
        _acc("Noise ColorFit Pro 5 Max Strap Pack", "Replacement strap 3-pack for Noise ColorFit Pro 5 Max.", "Street — ColorFit Strap Pack", "3 straps; quick release; ColorFit fit", 999),
        _acc("Spigen MagFit Car Mount", "Spigen MagSafe car vent mount for iPhone and MagSafe cases.", "Street — MagFit Car Mount", "MagSafe mount; vent; one-hand use", 2499),
        _acc("boAt Bassheads 900 Pro", "boAt Bassheads 900 Pro wired over-ear for gaming and calls.", "Street — Bassheads 900 Pro", "Wired; 40mm drivers; foldable", 2499),
        _acc("Samsung Galaxy Buds2 Pro", "Samsung Galaxy Buds2 Pro prior Buds still popular at discount.", "Street — Buds2 Pro", "ANC; 360 audio; IPX7; USB-C", 9999),
        _acc("Apple EarPods USB-C", "Apple EarPods with USB-C connector for iPhone buyers who skip wireless.", "Street — EarPods USB-C", "USB-C wired; Apple certified", 2000),
        _acc("OnePlus Warp Charge 100W Cable", "OnePlus Warp Charge 100W braided USB-C cable for SUPERVOOC phones.", "Street — Warp 100W Cable", "100W SUPERVOOC; braided; USB-C", 999),
        _acc("Anker 737 Power Bank 24000mAh 140W", "Anker 737 GaN power bank for laptop and phone fast charging.", "Street — Anker 737 24k", "24000mAh; 140W; GaN; USB-C", 12999),
        _acc("boAt Wave Sigma 3 Smartwatch", "boAt Wave Sigma 3 AMOLED Bluetooth calling smartwatch.", "Street — Wave Sigma 3", "AMOLED; BT calling; SpO2; IP68", 3999),
        _acc("Fire-Boltt Phoenix Ultra Smartwatch", "Fire-Boltt Phoenix Ultra premium AMOLED smartwatch.", "Street — Phoenix Ultra", "AMOLED; BT calling; sports modes", 4499),
        _acc("Samsung 15W Wireless Charger Stand", "Samsung 15W wireless charging stand for Galaxy phones and Buds.", "Street — 15W Wireless Stand", "15W wireless; stand; Samsung certified", 3499),
        _acc("Google Pixel Stand (3rd gen)", "Google Pixel Stand for Pixel phones with fan cooling and Hub features.", "Street — Pixel Stand 3", "Pixel Stand; 23W; Hub features; USB-C", 6999),
        _acc("Spigen Rugged Armor Pro for Galaxy S26 Plus", "Spigen Rugged Armor Pro case for Samsung Galaxy S26 Plus.", "Street — Rugged Armor S26 Plus", "Kickstand; dual layer; S26 Plus fit", 2799),
        _acc("Ringke Onyx Case for iPhone 17 Pro Max", "Ringke Onyx slim case for iPhone 17 Pro Max.", "Street — Onyx 17 Pro Max", "Slim; matte; precise cutouts; MagSafe optional", 1799),
        _acc("Nillkin Super Frosted Shield for Vivo X300 Pro", "Nillkin Super Frosted Shield case for Vivo X300 Pro.", "Street — Frosted X300 Pro", "Frosted PC; bumpers; X300 Pro fit", 1499),
        _acc("ESR HaloLock Wireless Car Charger 15W", "ESR MagSafe 15W wireless car charger mount.", "Street — HaloLock Car 15W", "MagSafe 15W; vent mount; one-hand", 3999),
        _acc("Ambrane Type-C to Lightning Cable 1m", "Ambrane MFi USB-C to Lightning cable for older iPhone accessories.", "Street — C-to-Lightning 1m", "MFi; USB-C to Lightning; 1m", 999),
        _acc("Zebronics Zeb-Sound Bomb N1 TWS", "Zebronics Zeb-Sound Bomb N1 budget TWS earbuds.", "Street — Sound Bomb N1", "TWS; gaming mode; long battery; USB-C", 1299),
    ]


def expand_phones() -> list[ProductTuple]:
    return list(
        chain(
            expand_prior_gen(),
            expand_foldable_extras(),
            expand_color_variants(),
            expand_storage_skus(),
            expand_extended_brands(),
            expand_extra_phones(),
        )
    )


def expand_accessories() -> list[ProductTuple]:
    return list(
        chain(
            expand_accessory_cases(),
            expand_accessory_screen_glass(),
            expand_accessory_audio_charging(),
        )
    )
