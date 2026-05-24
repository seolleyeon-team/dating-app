#!/usr/bin/env python3
"""
Seolleyeon AI Profile Prompt Builder v3

Purpose
-------
Build controlled, metadata-first prompts for Seolleyeon's
"AI에게 내 취향 알려주기" feature.

Core principles
---------------
- AI profiles are synthetic profile assets for cold-start preference learning.
- They should look like realistic adult university-student profile photos.
- They must not look like influencer shoots, idol profiles, school-uniform photos,
  or lightweight dating-app face-rating cards.
- Metadata is kept separate from prompt text so generation distribution can be audited.

Compatibility
-------------
Current CLIP code can read legacy storage paths such as:
    ai_profiles/female/137.png

This builder also emits v3 multi-shot paths such as:
    ai_profiles/female/137/face_card.png
    ai_profiles/female/137/silhouette_card.png
    ai_profiles/female/137/vibe_card.png

Recommended flow
----------------
1. Generate identity-level metadata.
2. Generate canonical face_card first.
3. Generate silhouette_card and vibe_card as same-person variations.
4. QA images manually or with vision checks.
5. Upload approved images to Firebase Storage.
6. Use profileId like female_137 / male_084 as recEvents.targetId.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple


Gender = Literal["female", "male"]
ShotType = Literal["face_card", "silhouette_card", "vibe_card"]

GENDERS: Tuple[Gender, ...] = ("female", "male")
SHOT_TYPES: Tuple[ShotType, ...] = ("face_card", "silhouette_card", "vibe_card")
SCHEMA_VERSION = "ai_profile_image_v3"
PROMPT_BUILDER_VERSION = "ai_profile_prompt_v4"
PROMPT_TARGETING_VERSION = "face_type_looks_level_targeting_v22"
METADATA_VERSION = "ai_profile_image_v4_compatible"
RARE_EYEWEAR_VARIATION_RATE = 0.0

FACE_TYPE_ORDER: Tuple[str, ...] = (
    "cat_like",
    "dog_like",
    "hamster_like",
    "bear_like",
    "fox_like",
    "deer_like",
    "horse_like",
    "mixed_neutral",
)
FACE_TYPE_ALIASES: Dict[str, str] = {
    "neutral_mixed": "mixed_neutral",
    "mixed_neutral": "mixed_neutral",
}
LOOKS_LEVEL_BANDS: Tuple[str, ...] = ("1.5-2.4", "2.5-3.2", "3.3-3.8", "3.9-4.3", "4.4-5.0")
LOOKS_LEVEL_BAND_RANGES: Dict[str, Tuple[float, float]] = {
    "1.5-2.4": (1.5, 2.4),
    "2.5-3.2": (2.5, 3.2),
    "3.3-3.8": (3.3, 3.8),
    "3.9-4.3": (3.9, 4.3),
    "4.4-5.0": (4.4, 5.0),
}

FACE_TYPE_TARGETS: Dict[str, Dict[str, int]] = {
    "global": {
        "cat_like": 34,
        "dog_like": 38,
        "hamster_like": 24,
        "bear_like": 29,
        "fox_like": 29,
        "deer_like": 43,
        "horse_like": 19,
        "mixed_neutral": 24,
    },
    "female": {
        "cat_like": 17,
        "dog_like": 19,
        "hamster_like": 12,
        "bear_like": 15,
        "fox_like": 14,
        "deer_like": 22,
        "horse_like": 9,
        "mixed_neutral": 12,
    },
    "male": {
        "cat_like": 17,
        "dog_like": 19,
        "hamster_like": 12,
        "bear_like": 14,
        "fox_like": 15,
        "deer_like": 21,
        "horse_like": 10,
        "mixed_neutral": 12,
    },
}

LOOKS_LEVEL_BAND_TARGETS: Dict[str, Dict[str, int]] = {
    "global": {"1.5-2.4": 36, "2.5-3.2": 108, "3.3-3.8": 72, "3.9-4.3": 24, "4.4-5.0": 0},
    "female": {"1.5-2.4": 18, "2.5-3.2": 54, "3.3-3.8": 36, "3.9-4.3": 12, "4.4-5.0": 0},
    "male": {"1.5-2.4": 18, "2.5-3.2": 54, "3.3-3.8": 36, "3.9-4.3": 12, "4.4-5.0": 0},
}

EYEWEAR_TARGETS: Dict[str, Dict[str, int]] = {
    "female": {"with_eyewear": 12, "without_eyewear": 108},
    "male": {"with_eyewear": 24, "without_eyewear": 96},
}
EYEWEAR_RESERVE_TARGETS: Dict[str, Dict[str, int]] = {
    "female": {"with_eyewear": 2, "without_eyewear": 18},
    "male": {"with_eyewear": 4, "without_eyewear": 16},
}
SEASON_TARGETS: Dict[str, int] = {"spring": 60, "summer": 53, "autumn": 79, "winter": 48}


# -----------------------------------------------------------------------------
# Visual translation maps
# -----------------------------------------------------------------------------

FACE_TYPE_WEIGHTS: Dict[str, float] = {
    "cat_like": 0.14,
    "dog_like": 0.16,
    "hamster_like": 0.10,
    "bear_like": 0.12,
    "fox_like": 0.12,
    "deer_like": 0.18,
    "horse_like": 0.08,
    "mixed_neutral": 0.10,
}

FACE_TYPE_VISUAL: Dict[str, str] = {
    "cat_like": (
        "almond-shaped eyes with slightly lifted outer corners, composed chic calm expression, "
        "moderately defined jawline, balanced cheek fullness, not as narrow or intense as fox-like; "
        "slightly sharper, neat, alert impression; avoid turning into mixed_neutral; avoid overly cute large-eye style"
    ),
    "dog_like": (
        "rounder eyes, soft cheeks, warm approachable expression, soft jawline, "
        "friendly adult student impression without puppy-like exaggeration or childlike cues; "
        "warm, approachable, rounded friendly impression; avoid deer_like long delicate face; avoid bear_like heavy square fullness; "
        "for low-band targets, dog_like warmth must stay plain, low-polish, and not upgraded by neat grooming or confident campus portrait styling"
    ),
    "hamster_like": (
        "compact rounded adult face, fuller cheeks, smaller soft nose impression, "
        "warm gentle presence, explicitly mature and not baby-faced or childlike; "
        "soft cheeks, compact and gentle impression; avoid babyface / childlike; adult proportions; "
        "especially in vibe_card, keep adult university-age signals and never let rounded softness read as underage"
    ),
    "bear_like": (
        "broader warm facial structure, grounded stable impression, thicker natural brows, "
        "soft sturdy jaw and cheek presence, calm reliable expression, avoid delicate deer-like oval softness; "
        "grounded, soft-solid impression; avoid deer_like delicate narrowness; avoid dog_like overly puppyish cuteness"
    ),
    "fox_like": (
        "subtle composed fox-like impression, slightly alert but ordinary campus face, "
        "slightly narrow eyes with restrained facial angularity, less round friendly softness than dog_like, "
        "calm composed expression rather than openly puppyish warmth, "
        "one or two visible but understated fox_like cues should remain present so the face does not collapse into mixed_neutral, "
        "avoid compact hamster-like cheek softness and avoid small rounded cute impression, "
        "natural non-glossy skin impression, no dramatic eye enlargement, no slim V-line jaw; "
        "fox_like does not mean highly attractive; fox_like does not mean celebrity/idol styling; "
        "fox_like should remain within the assigned looksLevelBand; "
        "avoid dog_like warm puppy impression, avoid round friendly puppy-like eyes, "
        "avoid overly soft cheeks and bubbly approachability, avoid cute dog-like warmth; "
        "avoid hamster_like compact round cuteness, avoid losing all fox_like cues into mixed_neutral balance; "
        "avoid deer_like elegant softness, avoid sharp handsome transformation, avoid over-level public-figure polish, "
        "avoid model-like refinement"
    ),
    "deer_like": (
        "soft oval face, medium-large calm eyes, delicate jawline, gentle quiet expression, "
        "calm intellectual mood, not the default for every soft face; gentle, calm, softer delicate impression; "
        "not automatically more attractive; avoid taking over other faceTypes"
    ),
    "horse_like": (
        "longer mature face proportion, higher nose bridge impression, defined cheekbones, "
        "elegant adult impression, realistic and not caricatured; longer facial impression, mature and calm; "
        "avoid caricature; adult grounded proportions"
    ),
    "mixed_neutral": (
        "balanced everyday facial proportions, medium eyes, softly defined jawline, "
        "ordinary real student profile impression, no single face-type cue dominates, avoid drifting into deer-like by default; "
        "balanced ordinary mixed impression; no strong animal-type cue; avoid drifting to deer_like attractiveness"
    ),
    "neutral_mixed": (
        "balanced everyday facial proportions, medium eyes, softly defined jawline, "
        "ordinary real student profile impression, no single face-type cue dominates, avoid drifting into deer-like by default; "
        "balanced ordinary mixed impression; no strong animal-type cue; avoid drifting to deer_like attractiveness"
    ),
}

LOOKS_LEVEL_BAND_VISUALS: Dict[str, str] = {
    "1.5-2.4": (
        "ordinary natural real student look, mild asymmetry acceptable, casual profile quality, "
        "not visually striking, not highly polished, do not improve the person above this band; "
        "very ordinary, plain, realistic everyday campus face; natural asymmetry; ordinary skin texture; "
        "no refined jawline; no large bright eyes; preserve a sincere and kind impression without attractiveness upgrade"
    ),
    "2.5-3.2": (
        "average to mildly pleasant everyday appearance, not attractive enough for 3.3-3.8, "
        "ordinary common campus profile impression with ordinary facial proportions, "
        "natural grooming with modest approachable realism, not highly styled; "
        "no dramatic facial refinement; no refined jawline; no noticeably sharp nose bridge; "
        "no enlarged bright eyes; no glossy smooth skin; no model-like symmetry; "
        "ordinary student realism with small natural asymmetry and everyday skin texture; "
        "keep facial attractiveness clearly below 3.3-3.8; "
        "do not let styling, lighting, or camera polish raise the perceived looks band; "
        "mild sincere impression is okay, but do not upgrade attractiveness; "
        "ordinary student realism is more important than attractiveness"
    ),
    "3.3-3.8": (
        "clearly attractive but realistic, balanced features and clean grooming, "
        "still ordinary enough for a real university student, no idealized symmetry or public-figure polish; "
        "neat and pleasant but still realistic; mildly attractive but not model-like; natural campus profile tone; "
        "avoid over-sharpened jaw, perfect symmetry, heavy retouching"
    ),
    "3.9-4.3": (
        "noticeably attractive and polished yet plausible as a real university student, use restraint, "
        "no idealized V-line jaw, no glossy skin, no stage-like styling; "
        "clearly attractive but still grounded and non-public-figure; trust-based profile realism; "
        "no 4.4-5.0 over-level public-figure look; no commercial photoshoot; no extreme beauty filter"
    ),
    "4.4-5.0": "forbidden over-level band for final approved dataset",
}

FACE_SHAPE_VISUAL: Dict[str, str] = {
    "soft_oval": "soft oval face shape",
    "round": "naturally rounded face shape",
    "soft_rectangular": "soft rectangular face shape",
    "slightly_long": "slightly longer face shape",
    "heart": "subtle heart-shaped face line",
    "balanced": "balanced natural face shape",
}

EYE_SIZE_VISUAL: Dict[str, str] = {
    "small_medium": "small-to-medium eyes",
    "medium": "medium-sized eyes",
    "medium_large": "medium-large eyes",
    "round_medium": "round medium eyes",
    "narrow_medium": "slightly narrow medium eyes",
}

EYE_TILT_VISUAL: Dict[str, str] = {
    "neutral": "neutral eye tilt",
    "slightly_lifted": "slightly lifted outer eye corners",
    "neutral_slight_downturned": "neutral to slightly downturned eye shape",
    "soft_downturned": "soft slightly downturned eye shape",
}

JAWLINE_VISUAL: Dict[str, str] = {
    "soft": "soft jawline",
    "soft_defined": "soft but defined jawline",
    "defined": "naturally defined jawline",
    "rounded": "rounded jawline",
    "slightly_angular": "slightly angular but realistic jawline",
}

CHEEK_VISUAL: Dict[str, str] = {
    "low": "subtle cheek fullness",
    "moderate": "moderate cheek fullness",
    "full": "fuller cheeks",
    "defined": "lightly defined cheekbones",
}

NOSE_VISUAL: Dict[str, str] = {
    "soft_low": "soft low-to-medium nose bridge",
    "soft_medium": "soft medium nose bridge",
    "medium": "natural medium nose bridge",
    "high_medium": "medium-high nose bridge",
}

LIP_VISUAL: Dict[str, str] = {
    "thin_natural": "natural thinner lips",
    "natural_medium": "natural medium lips",
    "soft_full": "soft fuller lips",
}

BROW_VISUAL: Dict[str, str] = {
    "light_natural": "light natural brows",
    "natural": "natural brows",
    "straight_natural": "natural straight brows",
    "thick_natural": "thicker natural brows",
}

SKIN_VISUAL: Dict[str, str] = {
    "natural": "natural skin texture",
    "natural_clear": "clear natural skin texture",
    "healthy": "healthy natural skin texture",
    "slightly_textured": "real skin texture with very mild imperfections",
}

VIBE_VISUAL: Dict[str, str] = {
    "soft": "soft and gentle mood",
    "chic": "subtle chic mood without looking cold",
    "intellectual": "calm intellectual mood",
    "sporty": "healthy sporty mood",
    "calm": "quiet calm mood",
    "warm": "warm sincere mood",
    "calm_intellectual": "calm intellectual mood",
    "warm_sporty": "warm sporty mood",
    "clear_trust": "clear trustworthy mood",
    "quiet_romance": "quiet romantic but mature mood",
}

BODY_FAT_VISUAL: Dict[str, str] = {
    "slim": "slim build",
    "soft_slim": "soft slim build",
    "healthy_average": "healthy average build",
    "average_soft": "average build with a soft natural body line",
    "fit_natural": "naturally fit build",
    "athletic_natural": "naturally athletic but not bodybuilder-like build",
    "solid_average": "solid average build",
}

FRAME_VISUAL: Dict[str, str] = {
    "small": "small frame",
    "small_medium": "small-to-medium frame",
    "medium": "medium frame",
    "medium_broad": "medium-to-broad frame",
    "broad": "broad frame",
}

MUSCULARITY_VISUAL: Dict[str, str] = {
    "low_natural": "low natural muscularity",
    "natural": "natural muscularity",
    "moderate_natural": "moderate natural muscularity",
    "athletic_moderate": "moderate athletic muscularity",
}

SHOULDER_VISUAL: Dict[str, str] = {
    "narrow": "narrow shoulders",
    "narrow_medium": "narrow-to-medium shoulders",
    "medium": "medium shoulder width",
    "medium_broad": "medium-broad shoulders",
    "broad": "broad shoulders",
}

WAIST_VISUAL: Dict[str, str] = {
    "straight": "straight natural waist line",
    "soft_defined": "softly defined waist",
    "defined": "naturally defined waist",
    "not_emphasized": "waist not strongly emphasized",
}

HIP_VISUAL: Dict[str, str] = {
    "narrow": "narrow hip line",
    "medium": "medium hip line",
    "soft_medium": "soft medium hip line",
    "not_emphasized": "hip line not emphasized",
}

LEG_RATIO_VISUAL: Dict[str, str] = {
    "balanced": "balanced leg proportion",
    "slightly_long": "slightly long leg proportion",
    "long": "long leg proportion while still realistic",
}

TORSO_VISUAL: Dict[str, str] = {
    "short_balanced": "slightly short but balanced torso length",
    "balanced": "balanced torso length",
    "slightly_long": "slightly longer torso length",
}

HEAD_BODY_RATIO_VISUAL: Dict[str, str] = {
    "realistic": "realistic adult head-to-body ratio",
    "slightly_small_head": "slightly small head-to-body impression but still realistic",
    "balanced": "balanced adult head-to-body ratio",
}

HAIR_LENGTH_VISUAL: Dict[str, str] = {
    "short": "short",
    "medium": "medium-length",
    "medium_long": "medium-long",
    "long": "long",
    "bob": "bob-length",
}

HAIR_TEXTURE_VISUAL: Dict[str, str] = {
    "soft_straight": "soft straight",
    "natural_straight": "natural straight",
    "slightly_wavy": "slightly wavy",
    "soft_wavy": "soft wavy",
    "textured": "soft textured",
}

HAIR_COLOR_VISUAL: Dict[str, str] = {
    "natural_black": "natural black",
    "natural_dark_brown": "natural dark brown",
    "dark_brown": "dark brown",
}

BANGS_VISUAL: Dict[str, str] = {
    "none": "no bangs",
    "side_bangs": "soft side bangs",
    "see_through_bangs": "light natural bangs",
    "soft_fringe": "soft natural fringe",
}

MAKEUP_VISUAL: Dict[str, str] = {
    "none": "no visible makeup, clean natural grooming",
    "light_natural": "light natural makeup",
    "natural": "natural makeup",
    "clean_grooming": "clean natural grooming",
}

FASHION_VISUAL: Dict[str, str] = {
    "campus_neat": "neat campus everyday fashion",
    "campus_casual": "casual campus everyday fashion",
    "minimal_clean": "minimal clean everyday fashion",
    "soft_romantic": "soft mature romantic everyday fashion",
    "sporty_casual": "sporty casual campus fashion",
    "intellectual_neat": "intellectual neat campus fashion",
    "classic_neat": "classic neat campus fashion",
    "mori_soft": "soft natural campus fashion",
    "dandy_cozy": "cozy neat campus fashion",
    "dandy_nerd": "bookish neat campus fashion",
    "street_vintage_soft": "soft vintage campus fashion",
    "gorpcore_clean": "clean functional campus fashion",
}

OUTFIT_FIT_VISUAL: Dict[str, str] = {
    "regular_fit": "regular fit",
    "relaxed_fit": "relaxed fit",
    "neat_regular": "neat regular fit",
    "slim_regular": "slim-regular fit without being tight",
}

FACE_CARD_OUTFITS: Dict[Gender, List[str]] = {
    "female": [
        "ivory knit cardigan over a simple inner top",
        "muted rose blouse with a light cardigan",
        "cream sweatshirt with a simple collar detail",
        "soft beige cardigan with a plain white top",
        "minimal navy knit top with a calm campus mood",
    ],
    "male": [
        "simple navy sweatshirt over a white T-shirt",
        "cream knit sweater with a clean crew neck",
        "light gray hoodie layered under a simple jacket",
        "minimal beige cardigan over a plain T-shirt",
        "clean oxford shirt under a casual knit vest",
    ],
}

FULL_BODY_OUTFITS: Dict[Gender, List[str]] = {
    "female": [
        "regular-fit light cardigan, relaxed straight pants, simple campus tote bag, clean sneakers",
        "soft knit top, ankle-length straight skirt, simple tote bag, clean flats or sneakers",
        "minimal sweatshirt, straight denim pants, canvas tote bag, clean sneakers",
        "neat blouse, regular-fit slacks, light cardigan, campus tote bag",
        "soft cardigan, relaxed wide-leg pants, minimal sneakers",
    ],
    "male": [
        "regular-fit navy sweatshirt, straight-fit beige chinos, simple backpack, clean sneakers",
        "cream knit sweater, straight denim pants, canvas backpack, clean sneakers",
        "casual jacket over a plain T-shirt, regular-fit slacks, simple backpack",
        "oxford shirt with a light knit vest, straight chinos, clean sneakers",
        "minimal hoodie, straight-fit dark pants, simple canvas bag, clean sneakers",
    ],
}

# Fallback only: normal vibe_card prompts sample from LOCATION_VIBE_ACTIVITIES.
VIBE_ACTIVITIES: Dict[Gender, List[str]] = {
    "female": [
        "standing with relaxed posture, calm everyday profile mood",
        "holding a simple tote or notebook, sincere ordinary student mood",
        "looking ahead naturally with a gentle expression, quiet lifestyle mood",
    ],
    "male": [
        "standing with relaxed posture, calm everyday profile mood",
        "holding a simple tote or notebook, sincere ordinary student mood",
        "looking ahead naturally with a gentle expression, quiet lifestyle mood",
    ],
}

LOCATION_VIBE_ACTIVITIES: Dict[str, List[str]] = {
    "campus_walkway": [
        "walking slowly with a canvas tote and a few notebooks, relaxed everyday student mood",
        "pausing beside a quiet path with a gentle expression, calm between-classes moment",
        "holding a light jacket while looking ahead naturally, sincere campus-day profile mood",
    ],
    "campus_cafe": [
        "reviewing a small notebook with a warm drink nearby, calm focused mood",
        "sitting at a small table with a phone screen turned away, quiet everyday break",
        "organizing study materials beside a simple cup, soft natural campus-cafe mood",
    ],
    "library_lounge": [
        "reading lecture notes with a few books nearby, quiet academic mood",
        "looking up from a notebook with a calm thoughtful expression, focused study break",
        "arranging papers and a pen on the table, sincere low-key study mood",
    ],
    "lecture_building_hallway": [
        "holding a folder and standing naturally near a quiet hallway wall, between-classes mood",
        "checking a closed notebook while waiting calmly, ordinary lecture-day profile mood",
        "walking with a backpack strap held lightly, relaxed academic routine mood",
    ],
    "student_union_lounge": [
        "sitting in a shared lounge chair with a notebook nearby, calm everyday student mood",
        "standing near neutral lounge seating with a relaxed sincere expression, casual campus moment",
        "sorting small study items in a public lounge area, natural low-pressure profile mood",
    ],
    "small_exhibition": [
        "looking thoughtfully at a simple abstract artwork, quiet cultural interest mood",
        "standing near a neutral display wall with a calm expression, understated exhibition visit mood",
        "holding a small plain brochure with no readable text, soft reflective profile mood",
    ],
    "bookstore_near_campus": [
        "browsing a shelf with book spines softly unreadable, calm curious mood",
        "holding one closed book at waist level, quiet bookstore profile moment",
        "standing near a simple bookshelf with a gentle expression, thoughtful everyday mood",
    ],
    "local_park_near_campus": [
        "sitting on a simple park bench with a tote beside them, peaceful afternoon mood",
        "walking along a quiet path with relaxed shoulders, calm outdoor profile mood",
        "standing near soft greenery while holding a light jacket, sincere everyday mood",
    ],
    "campus_garden": [
        "walking beside low greenery with a calm expression, soft campus garden mood",
        "standing near plants with relaxed posture, quiet fresh-air profile moment",
        "holding a notebook lightly while looking toward the path, gentle student-life mood",
    ],
    "campus_sports_court": [
        "resting after a casual activity with a plain water bottle, healthy ordinary mood",
        "standing near the side of a quiet court in modest casual clothes, relaxed active-day mood",
        "holding a light jacket after a casual walk, natural sporty campus mood",
    ],
    "quiet_study_room": [
        "reviewing notes at a clean desk with a closed laptop nearby, calm academic mood",
        "writing briefly in a notebook with a focused but relaxed expression, quiet study mood",
        "organizing stationery and papers on a simple desk, sincere student routine mood",
    ],
    "dorm_common_lounge": [
        "sitting in a shared common lounge with a book nearby, calm residential student mood",
        "standing near neutral lounge furniture with a gentle expression, ordinary shared-space mood",
        "holding a warm drink in a public common area, relaxed low-key profile mood",
    ],
    "neutral_outdoor_street_near_campus": [
        "walking along a quiet street with a simple tote, natural everyday profile mood",
        "standing near a low wall with soft background blur, calm casual street moment",
        "looking ahead while holding a light outerwear layer, relaxed near-campus mood",
    ],
    "seaside_walk": [
        "walking slowly near a simple railing with a light jacket, calm breezy profile mood",
        "standing with the horizon softly behind them, relaxed sincere outdoor mood",
        "sitting on a simple bench near the water with modest casual styling, peaceful everyday mood",
    ],
    "safe_mirror_snapshot": [
        "standing in front of a clean full-length mirror with the phone not covering the face, natural outfit-check mood",
        "adjusting a jacket lightly while facing a neutral mirror, calm ordinary profile moment",
        "taking a simple mirror snapshot with relaxed posture and visible face, understated everyday mood",
    ],
    "forest_bench": [
        "sitting on a wooden bench under soft trees with a small book nearby, quiet reflective mood",
        "resting with a tote beside them and relaxed shoulders, calm forest-path profile mood",
        "looking across a peaceful walking path from a bench, gentle nature-day mood",
    ],
    "casual_restaurant_table": [
        "sitting at a simple table with a modest meal plate nearby, warm everyday dining mood",
        "holding a glass of water beside a small dish, calm natural restaurant moment",
        "looking relaxed with food softly in the foreground, sincere casual meal profile mood",
    ],
    "amusement_park_daytime": [
        "walking through a bright daytime walkway with attractions softly blurred behind, cheerful but calm mood",
        "standing near a simple fence with relaxed posture, lighthearted everyday outing mood",
        "holding a small plain snack cup, gentle casual amusement-day mood",
    ],
    "travel_destination_casual": [
        "standing on a quiet unfamiliar street with a small crossbody bag, calm travel-day profile mood",
        "resting near a simple railing while looking at the scenery, natural low-key travel mood",
        "walking through a quiet local park or neighborhood path, relaxed everyday trip moment",
    ],
    "flower_viewing_path": [
        "walking beside a flower-lined path with relaxed shoulders, soft spring outing mood",
        "standing near blooming flowers with a gentle expression, calm natural profile moment",
        "sitting near a flower bed with a light cardigan or jacket, quiet seasonal outing mood",
    ],
}

VIBE_LOCATION_WEIGHTS: Dict[str, float] = {
    "campus_walkway": 10.0,
    "campus_cafe": 9.0,
    "library_lounge": 8.0,
    "lecture_building_hallway": 7.0,
    "student_union_lounge": 7.0,
    "quiet_study_room": 8.0,
    "bookstore_near_campus": 5.0,
    "local_park_near_campus": 6.0,
    "campus_garden": 6.0,
    "neutral_outdoor_street_near_campus": 5.0,
    "small_exhibition": 3.0,
    "dorm_common_lounge": 4.0,
    "campus_sports_court": 3.0,
    "seaside_walk": 2.0,
    "forest_bench": 3.0,
    "flower_viewing_path": 3.0,
    "safe_mirror_snapshot": 1.0,
    "casual_restaurant_table": 2.0,
    "amusement_park_daytime": 1.0,
    "travel_destination_casual": 1.0,
}

LEGACY_VIBE_ACTIVITY_REWRITES: Dict[str, str] = {
    "sitting by a window in a quiet campus cafe, reading lecture notes with a warm drink nearby": "reading lecture notes with a warm drink nearby, calm focused study mood",
    "walking slowly on a tree-lined campus path while holding a few books": "walking slowly while holding a few books, relaxed everyday campus mood",
    "standing in a small exhibition space and looking at a framed artwork": "looking thoughtfully at a framed artwork, quiet cultural interest mood",
    "sitting in a quiet library lounge with a notebook and tablet on the table": "reviewing notes with a notebook and tablet nearby, calm academic mood",
    "standing near a campus garden with a relaxed sincere expression": "standing with a relaxed sincere expression, gentle everyday mood",
    "sitting by a window in a quiet campus cafe, reviewing lecture notes with a warm drink nearby": "reviewing lecture notes with a warm drink nearby, calm focused study mood",
    "walking naturally on a tree-lined campus path with a backpack": "walking naturally with a backpack, relaxed everyday campus mood",
    "standing near an outdoor campus basketball court after a casual game, holding a water bottle": "resting after a casual activity while holding a water bottle, healthy ordinary mood",
    "sitting in a quiet library lounge with a notebook and laptop on the table": "reviewing notes with a notebook and laptop nearby, calm academic mood",
}

VIBE_ACTIVITY_LOCATION_PATTERN = re.compile(
    r"\b("
    r"campus cafe|study lounge|campus path|tree-lined campus path|small exhibition space|"
    r"library lounge|campus garden|outdoor campus basketball court|campus sports court|"
    r"local park|bookstore|lecture building hallway|student union lounge|dorm common lounge|"
    r"neutral outdoor street|seaside|beachside|mirror|forest|restaurant|amusement park|"
    r"travel|flower-lined"
    r")\b",
    re.IGNORECASE,
)

VIBE_LOCATIONS: List[str] = [
    "quiet campus cafe or study lounge, warm neutral interior, no brand logos, no readable text",
    "quiet university walkway with trees and neutral campus buildings, no visible school logo, no readable text",
    "small local exhibition space near campus, neutral walls, no readable text",
    "calm library lounge or study area, no visible school name, no readable text",
    "small park near campus with soft greenery, no identifiable personal information",
]

SKIN_TONE_VISUAL: Dict[str, str] = {
    "fair_warm": "fair warm skin tone with realistic natural texture",
    "light_rosy": "light skin tone with a subtle natural rosy undertone",
    "natural_beige": "natural beige Korean skin tone with realistic texture",
    "medium_warm": "medium warm beige skin tone with healthy natural texture",
    "sun_kissed": "slightly sun-kissed healthy skin tone",
    "warm_tan": "warm lightly tanned skin tone with natural texture",
}

EYEWEAR_VISUAL: Dict[str, str] = {
    "none": "no glasses",
    "thin_round_metal": "thin round metal-frame glasses",
    "black_acetate": "simple black acetate-frame glasses",
    "soft_rectangular_metal": "soft rectangular metal-frame glasses",
    "clear_frame": "subtle clear-frame glasses",
}

SEASON_VISUAL: Dict[str, str] = {
    "spring": "spring campus season",
    "summer": "summer campus season with modest light layers",
    "autumn": "autumn campus season",
    "winter": "winter campus season with readable silhouette",
}

WEATHER_VISUAL: Dict[str, str] = {
    "clear": "clear soft weather",
    "cloudy": "calm cloudy weather",
    "light_rain_after": "after light rain with clean pavement and no face obstruction",
    "snowy": "gentle snowy weather without hiding the face",
    "mild_breeze": "mild breeze with natural movement",
}

TIME_OF_DAY_VISUAL: Dict[str, str] = {
    "daylight": "natural daylight",
    "golden_hour": "soft golden-hour daylight",
    "early_evening": "early evening ambient daylight, still bright enough to read face and body",
}

TEMPERATURE_VISUAL: Dict[str, str] = {
    "warm": "warm temperature feel",
    "mild": "mild temperature feel",
    "cool": "cool temperature feel",
    "cold": "cold temperature feel with moderate layers",
}

LOCATION_CATALOG: Dict[str, Dict[str, Any]] = {
    "campus_walkway": {
        "scene": "quiet tree-lined university walkway with neutral buildings and a non-identifying background",
        "allowedShots": ["silhouette_card", "vibe_card"],
        "privacyRisk": "low",
        "logoTextRisk": "low",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "safe open campus path with non-identifiable background",
    },
    "campus_cafe": {
        "scene": "quiet campus cafe or study lounge with warm neutral interior",
        "allowedShots": ["face_card", "vibe_card"],
        "privacyRisk": "low",
        "logoTextRisk": "low",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "ordinary study-friendly cafe setting",
    },
    "library_lounge": {
        "scene": "calm library lounge or study area with neutral academic interior",
        "allowedShots": ["face_card", "vibe_card"],
        "privacyRisk": "low",
        "logoTextRisk": "low",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "quiet academic interior",
    },
    "lecture_building_hallway": {
        "scene": "neutral lecture building hallway with soft daylight and uncluttered walls",
        "allowedShots": ["silhouette_card", "vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "requires no visible logo, no readable text, no identifiable school name",
    },
    "student_union_lounge": {
        "scene": "student union lounge with neutral seating and soft daylight",
        "allowedShots": ["face_card", "vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "requires no visible logo, no readable text, no identifiable school name",
    },
    "small_exhibition": {
        "scene": "small local exhibition space near campus with neutral walls and softly blurred displays",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "low",
        "logoTextRisk": "low",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "quiet cultural visit without readable labels",
    },
    "bookstore_near_campus": {
        "scene": "small independent bookstore near campus with neutral shelves and softly blurred book spines",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "requires no visible logo, no readable text, no identifiable shop name",
    },
    "local_park_near_campus": {
        "scene": "small local park near campus with soft greenery and non-identifiable background",
        "allowedShots": ["silhouette_card", "vibe_card"],
        "privacyRisk": "low",
        "logoTextRisk": "low",
        "seasonCompatibility": ["spring", "summer", "autumn"],
        "notes": "ordinary near-campus outdoor setting",
    },
    "campus_garden": {
        "scene": "quiet campus garden with soft greenery and a non-identifying background",
        "allowedShots": ["silhouette_card", "vibe_card"],
        "privacyRisk": "low",
        "logoTextRisk": "low",
        "seasonCompatibility": ["spring", "summer", "autumn"],
        "notes": "calm garden setting",
    },
    "campus_sports_court": {
        "scene": "outdoor campus sports court after casual activity with a simple uncluttered background",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn"],
        "notes": "casual after-activity only, no visible logo, no readable text, no body-focused pose",
    },
    "quiet_study_room": {
        "scene": "quiet study room with neutral desk area and simple academic atmosphere",
        "allowedShots": ["face_card", "vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "requires no visible logo, no readable text, no identifiable school name",
    },
    "dorm_common_lounge": {
        "scene": "shared dorm common lounge with neutral seating and public residential-study atmosphere",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "shared public lounge only, no private intimate room",
    },
    "neutral_outdoor_street_near_campus": {
        "scene": "quiet neutral street near campus with soft daylight and non-identifiable storefronts",
        "allowedShots": ["silhouette_card", "vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "requires no visible logo, no readable text, no identifiable shop name",
    },
    "seaside_walk": {
        "scene": "quiet seaside walkway or beachside path with the sea softly in the background, modest casual clothes and calm daytime mood",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn"],
        "notes": "modest casual clothes, no swimsuit, no pool, no beach party, no body-focused styling, no nightlife",
    },
    "safe_mirror_snapshot": {
        "scene": "clean neutral full-length mirror in a simple public-safe hallway or studio-like corner, face visible, phone held low enough not to cover the face, soft natural indoor lighting",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "phone must not cover face, no bathroom, no gym, no bedroom, no private intimate room, no visible phone logo",
    },
    "forest_bench": {
        "scene": "quiet forest park bench or tree-lined walking path with soft natural greenery and a non-identifiable background",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "low",
        "logoTextRisk": "low",
        "seasonCompatibility": ["spring", "summer", "autumn"],
        "notes": "calm ordinary nature-day mood, no dark isolated forest, no horror or fantasy styling, face and body remain visible",
    },
    "casual_restaurant_table": {
        "scene": "small casual restaurant or simple dining table with modest food and a neutral interior, person remains the subject",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "food can appear but person remains subject, no alcohol, no bar, no readable menu, no visible logo",
    },
    "amusement_park_daytime": {
        "scene": "daytime amusement park walkway with attractions softly blurred in the background, lighthearted calm outing mood",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn"],
        "notes": "lighthearted but calm, no mascot, no children featured, no readable signs, no visible logo, no crowd-focused background",
    },
    "travel_destination_casual": {
        "scene": "quiet overseas-style local street, park, or neighborhood path with generic travel atmosphere and non-identifiable background",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "medium",
        "logoTextRisk": "medium",
        "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        "notes": "generic travel mood only, no famous landmark, no flags, no readable signs, no luxury hotel, no tourist influencer style",
    },
    "flower_viewing_path": {
        "scene": "flower-lined park path or garden walkway with seasonal flowers and natural profile-like framing",
        "allowedShots": ["vibe_card"],
        "privacyRisk": "low",
        "logoTextRisk": "low",
        "seasonCompatibility": ["spring", "autumn"],
        "notes": "soft seasonal outing mood, no wedding-like staging, no influencer photoshoot, no excessive romantic fantasy mood, no readable signs",
    },
}

LOCATION_MEDIUM_RISK_NEGATIVE_CONSTRAINTS: Tuple[str, ...] = (
    "visible logo",
    "brand logo",
    "readable text",
    "identifiable location",
)

LOCATION_NEGATIVE_CONSTRAINTS: Dict[str, Tuple[str, ...]] = {
    "campus_walkway": (
        "visible school logo",
        "readable text",
    ),
    "campus_cafe": (
        "visible logo",
        "readable text",
    ),
    "library_lounge": (
        "visible school name",
        "readable text",
    ),
    "lecture_building_hallway": (
        "visible school name",
        "readable text",
        "identifiable school name",
    ),
    "student_union_lounge": (
        "visible logo",
        "readable text",
        "identifiable school name",
    ),
    "small_exhibition": (
        "readable artwork labels",
        "readable text",
    ),
    "bookstore_near_campus": (
        "readable covers",
        "readable signs",
        "visible logo",
    ),
    "local_park_near_campus": (
        "identifiable personal information",
    ),
    "campus_garden": (
        "visible school logo",
        "readable text",
    ),
    "campus_sports_court": (
        "visible logo",
        "team marks",
        "readable text",
        "body-focused pose",
    ),
    "quiet_study_room": (
        "visible school name",
        "readable text",
    ),
    "dorm_common_lounge": (
        "private bedroom details",
        "private intimate room",
        "readable text",
    ),
    "neutral_outdoor_street_near_campus": (
        "visible logo",
        "readable text",
        "identifiable shop name",
    ),
    "seaside_walk": (
        "swimsuit",
        "bikini",
        "pool",
        "beach party",
        "revealing outfit",
        "body-focused styling",
    ),
    "safe_mirror_snapshot": (
        "bathroom",
        "gym",
        "bedroom",
        "bathroom mirror",
        "gym mirror",
        "bedroom mirror",
        "private intimate room",
        "locker room",
        "flash glare",
        "visible phone brand",
        "phone logo",
    ),
    "forest_bench": (
        "dark isolated forest",
        "horror mood",
        "fantasy forest",
        "hidden face",
        "hidden body",
    ),
    "casual_restaurant_table": (
        "alcohol",
        "bar",
        "readable menu",
        "brand logo",
        "pub",
        "nightclub",
    ),
    "amusement_park_daytime": (
        "visible logo",
        "brand logo",
        "mascot",
        "children featured",
        "readable signs",
        "influencer pose",
        "crowd-focused background",
    ),
    "travel_destination_casual": (
        "famous landmark",
        "flags",
        "national symbols",
        "readable signs",
        "luxury hotel",
        "tourist influencer style",
        "identifiable location",
    ),
    "flower_viewing_path": (
        "influencer photoshoot",
        "wedding-like staging",
        "excessive romantic fantasy mood",
        "readable signs",
    ),
}

SAFE_FASHION_CATALOG: Dict[Gender, Dict[str, Dict[str, Any]]] = {
    "female": {
        "campus_casual": {
            "outerwear": {"spring": ["light cardigan"], "summer": [None], "autumn": ["cotton overshirt"], "winter": ["short wool-blend jacket"]},
            "tops": ["plain sweatshirt", "soft hoodie", "simple collar knit"],
            "bottoms": ["straight denim pants", "relaxed cotton pants", "wide-leg casual pants"],
            "shoes": ["clean sneakers"],
            "bags": ["canvas_tote", "backpack"],
            "palettes": ["ivory and denim blue", "soft gray and navy", "oatmeal and muted green"],
            "material": "cotton knit and denim",
            "fit": "regular relaxed fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "minimal_clean": {
            "outerwear": {"spring": ["light cardigan"], "summer": [None], "autumn": ["simple jacket"], "winter": ["short neat coat"]},
            "tops": ["fine knit top", "plain oxford shirt", "simple crew-neck knit"],
            "bottoms": ["straight slacks", "straight denim pants", "relaxed ankle pants"],
            "shoes": ["clean sneakers", "simple flats"],
            "bags": ["shoulder_bag", "canvas_tote"],
            "palettes": ["white and charcoal", "navy and beige", "soft gray and cream"],
            "material": "cotton, light wool, and clean woven fabric",
            "fit": "neat regular fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "soft_romantic": {
            "outerwear": {"spring": ["soft cardigan"], "summer": ["thin cardigan"], "autumn": ["knit cardigan"], "winter": ["short soft coat"]},
            "tops": ["soft knit top", "muted blouse", "round-neck cardigan"],
            "bottoms": ["knee-or-longer skirt", "ankle-length straight skirt", "wide-leg pants"],
            "shoes": ["clean flats", "minimal sneakers"],
            "bags": ["shoulder_bag", "canvas_tote"],
            "palettes": ["muted rose and ivory", "cream and soft brown", "dusty pink and gray"],
            "material": "soft knit and matte woven fabric",
            "fit": "soft regular fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "intellectual_neat": {
            "outerwear": {"spring": ["light cardigan"], "summer": [None], "autumn": ["knit vest"], "winter": ["short duffle-style coat"]},
            "tops": ["oxford shirt", "knit vest over a shirt", "simple stripe-free shirt"],
            "bottoms": ["straight pants", "neat slacks", "relaxed chinos"],
            "shoes": ["clean sneakers", "simple loafers"],
            "bags": ["canvas_tote", "backpack"],
            "palettes": ["navy and cream", "soft brown and ivory", "gray and white"],
            "material": "cotton shirting and soft knit",
            "fit": "neat regular fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "classic_neat": {
            "outerwear": {"spring": ["simple blazer"], "summer": [None], "autumn": ["simple blazer"], "winter": ["short wool jacket"]},
            "tops": ["plain knit", "simple blouse", "clean shirt"],
            "bottoms": ["straight slacks", "long skirt", "straight denim pants"],
            "shoes": ["simple loafers", "clean sneakers"],
            "bags": ["shoulder_bag", "canvas_tote"],
            "palettes": ["navy and ivory", "charcoal and cream", "brown and soft gray"],
            "material": "matte woven fabric and knit",
            "fit": "classic regular fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "mori_soft": {
            "outerwear": {"spring": ["linen cardigan"], "summer": ["thin linen overshirt"], "autumn": ["soft cardigan"], "winter": ["short textured coat"]},
            "tops": ["linen shirt", "soft knit", "plain cotton blouse"],
            "bottoms": ["long skirt", "wide pants", "relaxed straight pants"],
            "shoes": ["simple flats", "minimal sneakers"],
            "bags": ["canvas_tote", "shoulder_bag"],
            "palettes": ["sage and ivory", "linen beige and muted blue", "soft brown and cream"],
            "material": "linen, cotton, and soft knit",
            "fit": "relaxed but readable fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "sporty_casual": {
            "outerwear": {"spring": ["light windbreaker"], "summer": [None], "autumn": ["casual windbreaker"], "winter": ["short fleece jacket"]},
            "tops": ["plain sweatshirt", "casual crew-neck top", "simple hoodie"],
            "bottoms": ["straight jogger pants", "relaxed track pants", "straight denim pants"],
            "shoes": ["clean sneakers"],
            "bags": ["backpack", "canvas_tote"],
            "palettes": ["navy and white", "gray and muted green", "cream and charcoal"],
            "material": "cotton fleece and matte nylon",
            "fit": "relaxed sport-casual fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
    },
    "male": {
        "campus_casual": {
            "outerwear": {"spring": ["light overshirt"], "summer": [None], "autumn": ["casual jacket"], "winter": ["short padded jacket with readable shape"]},
            "tops": ["plain T-shirt", "simple hoodie", "plain sweatshirt"],
            "bottoms": ["chinos", "straight denim pants", "relaxed cotton pants"],
            "shoes": ["clean sneakers"],
            "bags": ["backpack", "canvas_tote"],
            "palettes": ["navy and beige", "gray and denim blue", "cream and olive"],
            "material": "cotton and denim",
            "fit": "regular relaxed fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "minimal_clean": {
            "outerwear": {"spring": ["simple jacket"], "summer": [None], "autumn": ["minimal jacket"], "winter": ["short wool-blend coat"]},
            "tops": ["fine knit", "plain shirt", "clean crew-neck knit"],
            "bottoms": ["slacks", "straight denim pants", "relaxed chinos"],
            "shoes": ["clean sneakers", "simple loafers"],
            "bags": ["backpack", "shoulder_bag"],
            "palettes": ["white and charcoal", "navy and gray", "cream and black"],
            "material": "cotton, light wool, and matte woven fabric",
            "fit": "neat regular fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "dandy_cozy": {
            "outerwear": {"spring": ["light cardigan"], "summer": [None], "autumn": ["corduroy jacket"], "winter": ["calm short coat"]},
            "tops": ["warm knit", "plain shirt", "soft cardigan"],
            "bottoms": ["corduroy pants", "chinos", "straight slacks"],
            "shoes": ["simple loafers", "clean sneakers"],
            "bags": ["shoulder_bag", "backpack"],
            "palettes": ["brown and cream", "navy and oatmeal", "warm gray and ivory"],
            "material": "knit, corduroy, and cotton",
            "fit": "cozy regular fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "dandy_nerd": {
            "outerwear": {"spring": ["light cardigan"], "summer": [None], "autumn": ["knit vest"], "winter": ["short wool jacket"]},
            "tops": ["oxford shirt", "check shirt", "knit vest over a shirt"],
            "bottoms": ["chinos", "straight pants", "neat slacks"],
            "shoes": ["clean sneakers", "simple loafers"],
            "bags": ["backpack", "canvas_tote"],
            "palettes": ["navy and cream", "brown and white", "gray and muted blue"],
            "material": "cotton shirting and soft knit",
            "fit": "bookish regular fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "sporty_casual": {
            "outerwear": {"spring": ["light windbreaker"], "summer": [None], "autumn": ["casual windbreaker"], "winter": ["short fleece jacket"]},
            "tops": ["plain sweatshirt", "simple athletic crew-neck top", "casual hoodie"],
            "bottoms": ["track pants", "straight jogger pants", "relaxed cotton pants"],
            "shoes": ["clean sneakers"],
            "bags": ["backpack"],
            "palettes": ["navy and white", "gray and black", "cream and muted green"],
            "material": "cotton fleece and matte nylon",
            "fit": "relaxed sport-casual fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "street_vintage_soft": {
            "outerwear": {"spring": ["work jacket"], "summer": [None], "autumn": ["flannel overshirt"], "winter": ["short work jacket"]},
            "tops": ["plain T-shirt", "flannel shirt", "soft sweatshirt"],
            "bottoms": ["wide denim pants", "straight cotton pants", "relaxed chinos"],
            "shoes": ["clean sneakers"],
            "bags": ["backpack", "shoulder_bag"],
            "palettes": ["washed blue and cream", "brown and navy", "muted green and gray"],
            "material": "cotton twill, flannel, and denim",
            "fit": "relaxed but clean fit",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
        "gorpcore_clean": {
            "outerwear": {"spring": ["functional light jacket"], "summer": ["light nylon overshirt"], "autumn": ["clean functional jacket"], "winter": ["short outdoor-style jacket"]},
            "tops": ["plain sweatshirt", "simple knit", "clean crew-neck top"],
            "bottoms": ["nylon pants", "straight cargo-style pants", "relaxed cotton pants"],
            "shoes": ["clean sneakers"],
            "bags": ["backpack"],
            "palettes": ["olive and charcoal", "gray and navy", "cream and muted green"],
            "material": "matte nylon and cotton",
            "fit": "functional regular fit with face fully visible",
            "bottomVisible": True,
            "silhouetteReadable": True,
        },
    },
}

for _gender_fashion_catalog in SAFE_FASHION_CATALOG.values():
    for _fashion_entry in _gender_fashion_catalog.values():
        _fashion_entry.setdefault("modest", True)

PHOTO_REALISM_VISUAL: Dict[str, str] = {
    "ordinary_smartphone": "realistic ordinary smartphone profile photo with mild natural digital noise",
    "clean_smartphone": "clean smartphone photo, natural color, not glossy commercial photography",
    "casual_profile": "casual profile image with slightly imperfect everyday composition",
}

SPECIAL_CASE_CATALOG: Dict[str, Dict[str, Any]] = {
    "none": {
        "allowedShots": ["face_card", "silhouette_card", "vibe_card"],
        "allowed": True,
        "bottomVisibleOverride": None,
        "notes": None,
        "ratioWeight": 0.94,
    },
    "four_cut_photo": {
        "allowedShots": ["face_card", "vibe_card"],
        "allowed": True,
        "bottomVisibleOverride": False,
        "notes": "simple four-cut photo strip style, natural expression, no booth logo, no readable text, not over-filtered",
        "ratioWeight": 0.015,
    },
    "id_photo": {
        "allowedShots": ["face_card"],
        "allowed": True,
        "bottomVisibleOverride": False,
        "notes": "adult student ID-like neutral portrait, plain clothes, realistic and not high-school-like",
        "ratioWeight": 0.005,
    },
    "snowy_walk": {
        "allowedShots": ["silhouette_card", "vibe_card"],
        "allowed": True,
        "bottomVisibleOverride": None,
        "notes": "gentle winter campus walk, face visible, moderate layers, body shape still readable",
        "ratioWeight": 0.015,
    },
    "exhibition_visit": {
        "allowedShots": ["vibe_card"],
        "allowed": True,
        "bottomVisibleOverride": None,
        "notes": "quiet small exhibition visit, no readable artwork labels or text",
        "ratioWeight": 0.015,
    },
    "campus_sports_after_activity": {
        "allowedShots": ["vibe_card"],
        "allowed": True,
        "bottomVisibleOverride": None,
        "notes": "casual campus sports after-activity moment, no marked jersey, no body-focused pose",
        "ratioWeight": 0.01,
    },
}

BANNED_POSITIVE_TERMS: Tuple[str, ...] = (
    "school uniform",
    "교복",
    "swimsuit",
    "수영복",
    "bikini",
    "lingerie",
    "nightclub",
    "club",
    "bar",
    "LP bar",
    "idol",
    "celebrity",
    "influencer",
    "visible logo",
    "team logo",
    "brand logo",
    "North Face",
    "Nike",
    "Adidas",
    "Musinsa",
    "Barcelona",
    "Bayern",
    "children",
    "아이들과",
    "bathroom",
    "화장실",
    "hotel",
    "luxury hotel",
    "halter neck",
    "tank top",
    "crop top",
    "sexualized",
    "revealing",
    "body-emphasizing",
    "gym mirror",
    "mirror shot in bathroom",
    "balaclava",
    "face-covering mask",
    "sunglasses",
    "tinted lenses",
    "colored fashion lenses",
    "team jersey",
    "street_punk",
    "street punk",
    "glam",
    "ably",
    "teto",
    "face-covering gorpcore",
)
_CATALOG_SAFETY_VALIDATED = False

COMMON_NEGATIVE = (
    "Avoid: childlike appearance, teenager, school uniform, idol trainee look, "
    "celebrity lookalike, influencer photoshoot, glamour studio lighting, "
    "heavy retouching, plastic skin, exaggerated beauty filter, revealing outfit, "
    "swimsuit, lingerie, nightclub, party scene, neon lighting, sexualized pose, "
    "luxury hotel background, identifiable school logo, visible real university name, "
    "text, watermark, distorted face, distorted hands, extra fingers, unrealistic body proportions."
)

QA_CHECKLIST: List[str] = [
    "adult_visual_age_20_plus",
    "not_childlike_or_school_uniform",
    "not_influencer_or_celebrity_like",
    "not_glamour_studio_or_idol_profile",
    "no_revealing_or_sexualized_styling",
    "campus_or_neutral_context",
    "no_readable_school_logo_or_personal_text",
    "realistic_smartphone_profile_photo",
    "face_readable_for_face_card",
    "silhouette_readable_for_silhouette_card",
    "vibe_readable_for_vibe_card",
    "metadata_matches_image",
    "identity_consistent_across_shots",
    "eyewear_consistent_across_shots",
]


# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------


def _pick_weighted(rng: random.Random, weighted: Mapping[str, float]) -> str:
    keys = list(weighted.keys())
    weights = list(weighted.values())
    return rng.choices(keys, weights=weights, k=1)[0]


def _pick(rng: random.Random, values: Sequence[str]) -> str:
    if not values:
        raise ValueError("Cannot pick from an empty sequence.")
    return values[rng.randrange(len(values))]


def _visual(mapping: Mapping[str, str], key: Optional[str], fallback: str = "") -> str:
    if not key:
        return fallback
    return mapping.get(str(key), str(key).replace("_", " "))


def _join_nonempty(parts: Iterable[str], sep: str = ", ") -> str:
    cleaned = [p.strip().rstrip(".") for p in parts if p and p.strip()]
    return sep.join(cleaned)


def _canonical_face_type(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "mixed_neutral"
    return FACE_TYPE_ALIASES.get(raw, raw)


def looks_level_band(value: Any) -> str:
    try:
        level = float(value)
    except (TypeError, ValueError):
        return "2.5-3.2"
    if level <= 2.4:
        return "1.5-2.4"
    if level <= 3.2:
        return "2.5-3.2"
    if level <= 3.8:
        return "3.3-3.8"
    if level <= 4.3:
        return "3.9-4.3"
    if level <= 5.0:
        return "4.4-5.0"
    return "over_5.0"


def _profile_sort_key(spec: Mapping[str, Any]) -> Tuple[int, int]:
    gender_rank = 0 if spec.get("gender") == "female" else 1
    try:
        numeric = int(_profile_number_token(str(spec.get("profileId", ""))))
    except ValueError:
        numeric = 0
    return gender_rank, numeric


def _stable_stride(length: int) -> int:
    if length <= 1:
        return 1
    for stride in (37, 31, 29, 23, 19, 17, 13, 11, 7, 5, 3):
        if length % stride:
            return stride
    return 1


def _spread_values_by_counts(counts: Mapping[str, int], order: Sequence[str], *, seed: int) -> List[str]:
    values: List[str] = []
    for key in order:
        values.extend([key] * max(0, int(counts.get(key, 0))))
    n = len(values)
    if n <= 1:
        return values
    stride = _stable_stride(n)
    positions = [(index * stride + int(seed)) % n for index in range(n)]
    out = [""] * n
    for value, position in zip(values, positions):
        out[position] = value
    return out


def _scale_counts_largest_remainder(
    targets: Mapping[str, int],
    *,
    count: int,
    order: Sequence[str],
) -> Dict[str, int]:
    total = sum(max(0, int(targets.get(key, 0))) for key in order)
    if count <= 0:
        return {key: 0 for key in order}
    if total <= 0:
        out = {key: 0 for key in order}
        out[order[0]] = count
        return out
    raw = {key: max(0, int(targets.get(key, 0))) * int(count) / total for key in order}
    base = {key: int(raw[key]) for key in order}
    remaining = int(count) - sum(base.values())
    ranked = sorted(order, key=lambda key: (raw[key] - base[key], int(targets.get(key, 0)), key), reverse=True)
    for key in ranked[:remaining]:
        base[key] += 1
    return base


def _gender_target_counts(
    targets: Mapping[str, Any],
    gender: Gender,
    count: int,
    order: Sequence[str],
) -> Dict[str, int]:
    source = targets.get(gender) if isinstance(targets.get(gender), Mapping) else targets
    normalized = {key: int(source.get(key, 0)) for key in order} if isinstance(source, Mapping) else {key: 0 for key in order}
    if sum(normalized.values()) == int(count):
        return normalized
    return _scale_counts_largest_remainder(normalized, count=int(count), order=order)


def _eyewear_target_counts(targets: Mapping[str, Any], gender: Gender, count: int) -> Dict[str, int]:
    source = targets.get(gender) if isinstance(targets.get(gender), Mapping) else {}
    source = source if isinstance(source, Mapping) else {}
    with_default = int(source.get("with_eyewear", round(0.1 * count if gender == "female" else 0.2 * count)))
    without_default = int(source.get("without_eyewear", max(0, int(count) - with_default)))
    counts = {"with_eyewear": max(0, with_default), "without_eyewear": max(0, without_default)}
    if sum(counts.values()) == int(count):
        return counts
    return _scale_counts_largest_remainder(counts, count=int(count), order=("with_eyewear", "without_eyewear"))


def _weather_for_season(season: str, rng: random.Random) -> str:
    options = {
        "spring": ["clear", "cloudy", "mild_breeze", "light_rain_after"],
        "summer": ["clear", "cloudy", "mild_breeze", "light_rain_after"],
        "autumn": ["clear", "cloudy", "mild_breeze"],
        "winter": ["clear", "cloudy", "snowy"],
    }
    return _pick(rng, options.get(season, options["spring"]))


def _temperature_for_season(season: str, weather: str) -> str:
    if season == "summer":
        return "warm"
    if season == "winter" or weather == "snowy":
        return "cold"
    if season == "autumn":
        return "cool"
    return "mild"


def _profile_number_token(profile_id: str) -> str:
    m = re.match(r"^(female|male)_(\d+)$", str(profile_id))
    if not m:
        raise ValueError(f"Invalid profileId: {profile_id}. Expected female_137 or male_084.")
    return m.group(2)


def make_profile_id(gender: Gender, numeric_id: int, *, width: int = 3) -> str:
    if gender not in GENDERS:
        raise ValueError(f"gender must be one of {GENDERS}")
    if numeric_id <= 0:
        raise ValueError("numeric_id must be positive")
    token = str(int(numeric_id)).zfill(max(0, int(width))) if width else str(int(numeric_id))
    return f"{gender}_{token}"


def is_ai_profile_id(profile_id: str) -> bool:
    return bool(re.match(r"^(female|male)_\d+$", str(profile_id or "")))


def storage_paths(profile_id: str, shot_type: Optional[ShotType] = None) -> Dict[str, str]:
    """Return legacy and v3 storage paths for an AI profile."""
    m = re.match(r"^(female|male)_(\d+)$", str(profile_id))
    if not m:
        raise ValueError(f"Invalid profileId: {profile_id}")
    gender, pid = m.group(1), m.group(2)
    out = {
        "legacy": f"ai_profiles/{gender}/{pid}.png",
        "face_card": f"ai_profiles/{gender}/{pid}/face_card.png",
        "silhouette_card": f"ai_profiles/{gender}/{pid}/silhouette_card.png",
        "vibe_card": f"ai_profiles/{gender}/{pid}/vibe_card.png",
    }
    if shot_type is not None:
        return {"legacy": out["legacy"], "storagePath": out[shot_type]}
    return out


def looks_level_to_visual(level: float) -> str:
    """Translate internal looksLevel into non-gamified visual language."""
    band = looks_level_band(float(level))
    return LOOKS_LEVEL_BAND_VISUALS.get(band, LOOKS_LEVEL_BAND_VISUALS["2.5-3.2"])


def face_type_target_visual(face_type: Any) -> str:
    """Return the canonical visual geometry block for a faceType target."""
    canonical = _canonical_face_type(face_type)
    return FACE_TYPE_VISUAL.get(canonical, FACE_TYPE_VISUAL["mixed_neutral"])


def looks_level_band_target_visual(band: Any) -> str:
    """Return the canonical visual calibration block for a looksLevelBand target."""
    key = str(band or "2.5-3.2")
    return LOOKS_LEVEL_BAND_VISUALS.get(key, LOOKS_LEVEL_BAND_VISUALS["2.5-3.2"])


def build_face_type_target_block(spec: Mapping[str, Any], shot_type: ShotType = "face_card") -> str:
    face = spec.get("face", {}) if isinstance(spec.get("face"), Mapping) else {}
    face_type = _canonical_face_type(face.get("faceType", "mixed_neutral"))
    block = face_type_target_visual(face_type)
    if shot_type == "face_card" and face_type == "fox_like":
        block += (
            "; face_card comparison guard: fox_like should not be interpreted as dog_like; "
            "keep fox_like cues subtle and composed; do not soften into a rounded puppy-like friendly look; "
            "do not compact into hamster_like rounded cuteness; do not become fully mixed_neutral; "
            "keep restrained angularity without making the person more attractive"
        )
    if shot_type == "face_card" and face_type == "cat_like":
        band = str(face.get("looksLevelBand") or looks_level_band(float(face.get("looksLevel", 3.0))))
        if band == "1.5-2.4":
            block += (
                "; cat_like 1.5-2.4 low-band no-upgrade lock: keep only a plain low-band cat_like cue, "
                "subtle almond-eye lift without neat fox_like polish; do not convert ordinary cat_like into fox_like neatness; "
                "do not make the face sharper, cleaner, brighter-eyed, or more composed than a very ordinary campus student; "
                "v22 face-card cat_like low-band hard lock: face_card itself must not read bear_like, hamster_like, mixed_neutral, or 2.5-3.2; "
                "avoid broad jaw, thick brows, sturdy fullness, compact rounded cuteness, balanced neutral prettiness, and black-acetate intellectual neatness upgrading the face; "
                "keep a visibly plain adult cat_like almond-eye cue with low polish and below-average ordinariness"
            )
        if band == "3.9-4.3":
            block += (
                "; face_card high-band cat_like guard: preserve clearly cat_like almond-eye lift, composed alert neatness, "
                "and slightly sharper clean structure so it does not soften into deer_like; keep it in 3.9-4.3 with neat campus polish, "
                "but avoid influencer, celebrity, model, idol, luxury, or beauty-filter styling"
            )
    return (
        f"Target faceType {face_type}: {block}. "
        "Use these as visible facial-geometry cues, not just a label; keep the target distinct from neighboring types."
    )


def build_face_card_depolish_block(spec: Mapping[str, Any]) -> str:
    face = spec.get("face", {}) if isinstance(spec.get("face"), Mapping) else {}
    band = str(face.get("looksLevelBand") or looks_level_band(float(face.get("looksLevel", 3.0))))
    parts = [
        "Face-card no-upgrade calibration: ordinary smartphone-like profile framing",
        "very ordinary phone camera profile feel",
        "flatter everyday lighting",
        "no portrait-style depth",
        "no dramatic catchlights",
        "no polished dating-profile crop",
        "facial realism over styling",
        "soft plain lighting without studio-beauty effect",
        "natural skin texture",
        "slight everyday imperfection",
        "no high-end portrait retouching",
        "no beauty-filter glow",
        "no commercial headshot style",
        "no social-media profile polish",
        "no face slimming",
        "no jaw sharpening",
        "no eye enlargement",
        "no nose refinement",
        "no glossy skin",
        "no professional headshot polish",
        "no public-figure or model expression",
        "no observed looksLevelBand upward drift",
    ]
    if band == "2.5-3.2":
        parts.extend([
            "if target looksLevelBand is 2.5-3.2, do not let observed appearance enter 3.3-3.8",
            "maintain average-to-mildly-pleasant appearance even if clothing, location, or lighting is neat",
            "neat styling must not raise facial attractiveness",
        ])
    face_type_for_depolish = _canonical_face_type(face.get("faceType", "mixed_neutral"))
    if face_type_for_depolish == "deer_like" and band == "2.5-3.2":
        parts.extend([
            "v22 deer_like 2.5-3.2 face-card no-upgrade lock",
            "gentle deer_like calmness must not read as above-average 3.3-3.8 elegance",
            "avoid confident portrait expression, refined delicate jawline, bright attractive eyes, soft golden glow, and polished cafe/profile styling",
            "keep deer_like softness ordinary, modest, and only average-to-mildly-pleasant",
        ])
    if face_type_for_depolish == "cat_like" and band == "1.5-2.4":
        parts.extend([
            "v22 cat_like low-band face-card anti-bear/hamster lock",
            "black acetate or neat styling must not make the face smarter, sturdier, rounder, cuter, or 2.5-3.2",
            "avoid bear_like broad jaw and thick-brow sturdiness",
            "avoid hamster_like compact rounded cuteness",
            "preserve plain almond-eye cat_like cues with low-band ordinariness",
        ])
    if face_type_for_depolish == "dog_like" and band == "1.5-2.4":
        parts.extend([
            "v22 dog_like low-band adult-boundary lock",
            "the face must read clearly adult university age, not borderline youthful or teen-like",
            "use mature adult proportions, adult jaw/neck/shoulder cues, and restrained adult grooming while staying plain 1.5-2.4",
            "avoid babyface softness, school-age styling, cute puppy expression, and youthful rounded proportions",
        ])
    if face_type_for_depolish == "dog_like" and band in {"1.5-2.4", "2.5-3.2"}:
        parts.extend([
            "dog_like warmth must remain ordinary and must not act as an attractiveness upgrade",
            "friendly warmth must stay ordinary, low-key, and unpolished",
            "for 1.5-2.4 dog_like, keep grooming, lighting, and pose so plain that QA still reads low-band rather than 2.5-3.2",
            "confident campus portrait styling must not make a low-band dog_like face look average-mildly pleasant",
            "avoid polished warmth",
            "avoid bright attractive smile",
            "avoid cute or handsome read",
            "avoid refined skin or refined face shape",
        ])
    return "; ".join(parts) + "."


def build_looks_level_target_block(spec: Mapping[str, Any], shot_type: ShotType = "face_card") -> str:
    face = spec.get("face", {}) if isinstance(spec.get("face"), Mapping) else {}
    level = float(face.get("looksLevel", 3.0))
    band = str(face.get("looksLevelBand") or looks_level_band(level))
    band_visual = looks_level_band_target_visual(band)
    face_type = _canonical_face_type(face.get("faceType", "mixed_neutral"))
    guard = ""
    if face_type == "fox_like" and band == "2.5-3.2":
        strength = "Target-specific face_card guard" if shot_type == "face_card" else "Combined fox_like 2.5-3.2 guard"
        guard = (
            f" {strength}: keep the fox_like impression subtle and composed, but ordinary; "
            "do not soften it into dog_like puppy warmth and do not sharpen it into model-like attractiveness; "
            "do not compress it into hamster_like rounded cuteness and do not flatten it into mixed_neutral when subtle fox_like cues are visible; "
            "preserve one or two understated fox_like cues such as slightly narrow eyes or a restrained alert expression without increasing attractiveness; "
            "avoid dog_like puppy warmth; avoid deer_like elegant softness; avoid sharp handsome transformation; "
            "avoid compact hamster-like softness; avoid fully balanced mixed_neutral face; "
            "avoid model-like profile; preserve the average-to-mildly-pleasant 2.5-3.2 band; "
            "do not let camera, lighting, styling, or pose raise it into 3.3-3.8."
        )
        if shot_type == "vibe_card":
            guard += (
                " v21 fox_like 2.5-3.2 vibe no-upgrade lock: lifestyle context must not turn restrained fox_like into clearly attractive 3.3-3.8; "
                "avoid bookstore/cafe polish, flattering golden light, neat jacket styling, confident profile pose, and composed cinematic mood when they raise attractiveness; "
                "keep the activity secondary, ordinary, and slightly unpolished so QA still chooses 2.5-3.2."
            )
    if face_type == "dog_like" and band in {"1.5-2.4", "2.5-3.2"}:
        if band == "1.5-2.4":
            dog_guard = (
                " Combined dog_like 1.5-2.4 guard: friendly does not mean cute or handsome; "
                "friendly does not mean higher attractiveness; very ordinary, plain, low-key, not conventionally attractive; "
                "warm approachable expression must stay unpolished and ordinary; avoid polished warmth; "
                "avoid bright attractive smile; avoid refined skin; avoid refined face shape; avoid large bright eyes; "
                "v15 dog_like low-band anti-overread: neat grooming, clean lighting, steady posture, or confident campus portrait styling must not be enough to read 2.5-3.2; "
                "v16 dog_like low-band no-polish rescue: keep the face deliberately plain enough that QA should still choose 1.5-2.4 over 2.5-3.2; "
                "use flatter everyday light, modest expression, mild asymmetry, ordinary skin texture, slightly imperfect grooming, and no likable portrait polish while keeping adult Korean university realism; "
                "v19 dog_like 1.5-2.4 full-shot hard lock: every shot, including face_card, must read below average, plain, and non-polished; "
                "QA must not read bear_like sturdiness, neat average appeal, or 2.5-3.2 mild pleasantness; "
                "keep dog_like cues as soft round eyes and approachable warmth only, without broad jaw, thick-brow sturdy bear_like structure, confident neatness, or cute/handsome charm; "
                "use visibly ordinary facial asymmetry, flatter skin texture, modest non-smiling expression, and unremarkable grooming so the face stays 1.5-2.4; "
                "preserve sincere campus realism without upgrading beyond 1.5-2.4."
                " v22 dog_like low-band age safety lock: every shot must read as a clearly adult university student, not borderline youthful; "
                "keep adult facial proportions, mature enough neck/jaw/shoulder cues, restrained adult grooming, and no cute puppy-like teenage softness while preserving the 1.5-2.4 plain band."
            )
            if shot_type in {"silhouette_card", "vibe_card"}:
                dog_guard += (
                    " Dependent-shot dog_like 1.5-2.4 lock: keep the referenced face visibly in the 1.5-2.4 band even in full-body, campus, or activity context; "
                    "do not let outfit, posture, outdoor lighting, glasses, or friendly action upgrade the dependent shot into 2.5-3.2; "
                    "match the face_card's plain low-band ordinariness exactly."
                )
            if shot_type == "vibe_card":
                dog_guard += (
                    " v16 dog_like low-band vibe no-upgrade lock: the lifestyle activity is quiet and ordinary, not a polished confident campus portrait; "
                    "activity context, outfit, location, and candid posture must not add average-pleasant appeal; "
                    "keep rounded friendly dog_like anchors low-key, with no longer mature horse_like elongation and no attractiveness upgrade from candid context. "
                    "v18 dog_like 1.5-2.4 vibe strict plainness lock: QA must still choose 1.5-2.4 for the vibe_card, not 2.5-3.2; "
                    "avoid any neat outfit-check, mirror/selfie, cafe, lounge, or campus activity that makes the person read average-to-mildly-pleasant; "
                    "use plain expression, flatter everyday lighting, ordinary phone snapshot texture, unstyled low-key grooming, mild asymmetry, and no warm polished smile; "
                    "v19 dog_like low-band vibe hard reject avoidance: do not use lounge-chair, notebook, cafe, clean crew-neck, short wool coat, or any tidy lifestyle setup that reads neat likable 2.5-3.2; "
                    "prefer plainer, less flattering campus context, neutral ordinary clothing, subdued posture, and an everyday unposed face where dog_like warmth is visible but not cute, handsome, sturdy, or polished; "
                    "the activity must feel secondary and unflattering enough to preserve the face_card's low-band ordinariness while remaining adult, realistic, and trustworthy."
                )
            accessories = spec.get("accessories", {}) if isinstance(spec.get("accessories"), Mapping) else {}
            if shot_type == "silhouette_card" and shot_eyewear_expected(accessories, shot_type) != "none":
                dog_guard += (
                    " dog_like eyewear silhouette low-band lock: glasses must not make the face read smarter, neater, or 2.5-3.2; "
                    "plain low-band dog_like ordinariness remains visible behind the glasses; "
                    "keep warm expression ordinary and unpolished even while eyewear remains clearly visible."
                )
        else:
            dog_guard = (
                " Combined dog_like 2.5-3.2 guard: average or mildly pleasant only; "
                "warmth must not raise looksLevelBand into 3.3-3.8; friendly warmth must stay ordinary; "
                "do not push warmth into cute, handsome, polished, or highly attractive; "
                "keep ordinary student proportions, ordinary skin texture, and below-3.3 facial attractiveness."
            )
        guard += dog_guard
    if face_type == "cat_like" and band == "1.5-2.4":
        guard += (
            " cat_like 1.5-2.4 low-band no-upgrade lock: plain low-band cat_like with mild almond-eye cue only; "
            "do not convert ordinary cat_like into fox_like neatness, deer_like delicacy, or 2.5-3.2 neat everyday appeal; "
            "do not let neat styling read as 2.5-3.2 or 3.3-3.8; "
            "keep mild asymmetry, ordinary skin texture, small imperfections, and low-key campus realism across this shot. "
            "v13 cat_like 1.5-2.4 reject-neatness lock: a clean campus outfit or sincere expression must not raise observedLooksLevelBand above 1.5-2.4; "
            "prefer plainer facial balance over likable polish; preserve ordinary asymmetry, flatter light, and non-refined eye-mouth balance. "
            "v22 cat_like low-band all-shot anti-misread lock: QA must not choose bear_like, hamster_like, mixed_neutral, or 2.5-3.2; "
            "avoid broad sturdy jaw, thick brows, heavy lower face, compact cheek cuteness, rounded hamster softness, and balanced neutral prettiness; "
            "black-acetate glasses must remain only an identity accessory and must not add intellectual neatness or average appeal."
        )
        if shot_type in {"silhouette_card", "vibe_card"}:
            guard += (
                " v18 cat_like low-band dependent-shot lock: match the face_card's very ordinary 1.5-2.4 cat_like ordinariness exactly; "
                "QA must still choose 1.5-2.4 rather than 2.5-3.2; "
                "do not let neat outfit, calm activity, or campus lighting create average-pleasant appeal; "
                "preserve subtle almond-eye cat_like cue without converting to dog_like, bear_like, or mixed_neutral; "
                "do not let dependent-shot distance, relaxed expression, or lifestyle context hide the low-band cat_like face."
            )
            if shot_type == "silhouette_card":
                guard += (
                    " v21 cat_like 1.5-2.4 silhouette no-upgrade lock: the full-body shot must still read low-band, not mixed_neutral 2.5-3.2; "
                    "avoid neat everyday outfit, clean posture, flattering distance, or balanced neutral face that raises the silhouette into average appeal; "
                    "keep plain low-band cat_like asymmetry and unpolished face readable even while preserving body silhouette."
                )
        accessories = spec.get("accessories", {}) if isinstance(spec.get("accessories"), Mapping) else {}
        if shot_type == "silhouette_card" and shot_eyewear_expected(accessories, shot_type) != "none":
            guard += (
                " v13 cat_like eyewear silhouette double lock: thin round metal glasses stay visible without making the face read neater; "
                "do not let glasses, library context, or clean styling upgrade the face into 2.5-3.2; "
                "keep the referenced low-band cat_like face plain behind the required visible frames."
            )
    if face_type == "cat_like" and band == "3.9-4.3" and shot_type in {"silhouette_card", "vibe_card"}:
        guard += (
            " v21 cat_like 3.9-4.3 dependent no-undershoot lock: dependent shots must preserve high-band cat_like polish and should not fall to 3.3-3.8; "
            "keep composed almond-eye lift, alert neatness, and slightly sharper clean structure visible despite lifestyle context or full-body distance; "
            "avoid small-face uncertainty, overly casual styling, flat light, or relaxed pose that makes QA lower the band while still avoiding celebrity/influencer 4.4-5.0."
        )
    if face_type == "mixed_neutral" and band == "3.3-3.8":
        guard += (
            " Mixed_neutral 3.3-3.8 guard: keep the face balanced and neutral, but clearly within the 3.3-3.8 mildly-attractive campus band; "
            "do not undershoot into 2.5-3.2 ordinary/plain; maintain neat grooming, balanced feature harmony, and moderate polish; "
            "avoid celebrity, influencer, model, luxury, or over-retouched styling while preserving above-average but sincere student realism."
        )
        if shot_type == "silhouette_card":
            guard += (
                " v20 mixed_neutral 3.3-3.8 silhouette no-undershoot lock: the full-body shot must still read as 3.3-3.8, not neat everyday 2.5-3.2; "
                "preserve the face_card's moderate polish, balanced feature harmony, clean grooming, and mildly attractive campus impression in the visible face; "
                "do not let distance, side angle, flat lighting, casual pose, or outfit reduce the face into ordinary/plain 2.5-3.2."
            )
    if shot_type in {"silhouette_card", "vibe_card"} and face_type == "hamster_like" and band == "2.5-3.2":
        guard += (
            " Dependent-shot hamster_like 2.5-3.2 identity lock: keep the referenced compact rounded adult face and fuller-cheek hamster_like impression visible; "
            "do not sharpen into fox_like, do not slim the face, do not raise the dependent shot into 3.3-3.8, and do not let black acetate glasses or standing posture create a smarter sharper higher-band read; "
            "match the face_card's average-to-mildly-pleasant 2.5-3.2 ordinariness exactly."
        )
        if shot_type == "silhouette_card":
            guard += (
                " v16 hamster_like silhouette compact-round lock: preserve compact rounded same-person cues from the face_card, including fuller cheeks, soft small-nose impression, and gentle adult roundedness; "
                "do not broaden into bear_like, do not widen the jaw, and do not make the brows or posture feel sturdy; "
                "avoid broad jaw, thick brows, sturdy bear_like fullness, or grounded heavy facial structure while keeping the full-body silhouette readable."
            )
        if shot_type == "vibe_card":
            guard += (
                " v12 hamster_like vibe anti-bear lock: do not broaden into bear_like grounded fullness; "
                "keep compact rounded adult cheeks visible in the lifestyle context; "
                "activity and posture must not make the face broader or sturdier; "
                "avoid thick-browed, broad-jawed, solid bear_like reinterpretation. "
                "v15 hamster_like vibe adult-boundary lock: rounded softness must remain clearly adult university age; "
                "include mature-enough styling and proportions, no babyface emphasis, no teenager cues, and no underage interpretation while keeping soft hamster_like cues. "
                "v21 hamster_like 2.5-3.2 vibe no-upgrade lock: rounded compact softness must not become cute, polished, or clearly attractive 3.3-3.8 in lifestyle context; "
                "avoid flattering cafe/bookstore/garden activity, warm polished smile, clean outfit showcase, and soft beauty lighting that upgrades the face; "
                "keep the vibe ordinary, phone-snapshot-like, mildly pleasant at most, and anchored to the face_card's 2.5-3.2 ordinariness."
            )
    if shot_type == "silhouette_card" and face_type == "deer_like" and band == "3.3-3.8":
        guard += (
            " Silhouette deer_like 3.3-3.8 readability lock: keep the soft oval face, calm medium-large eyes, delicate jawline, and gentle quiet deer_like impression readable at full-body distance; "
            "do not flatten into mixed_neutral, do not obscure the face, and keep enough facial pixels for target faceType verification without turning it into a headshot. "
            "v20 deer_like silhouette face-angle lock: never use a side-facing silhouette when deer_like faceType must be judged; use front-facing or mild three-quarter face angle with both eyes/nose-mouth balance readable; "
            "do not let body silhouette priority, walking pose, winter layers, or profile angle make the face type unclear; keep the face large and clear enough for QA to choose deer_like confidently."
        )
    if face_type == "deer_like" and band == "2.5-3.2" and shot_type == "face_card":
        guard += (
            " v22 deer_like 2.5-3.2 face-card no-upgrade lock: deer_like calmness must stay ordinary and must not become elegant 3.3-3.8; "
            "avoid confident attractive direct gaze, refined delicate jawline, bright large eyes, soft golden-hour portrait glow, and polished profile framing; "
            "keep the face average-to-mildly-pleasant only, with modest grooming, flatter light, small natural asymmetry, and no above-average campus appeal."
        )
    return (
        f"Target looksLevelBand {band} with internal level {level:.1f}: {band_visual}. "
        "LooksLevel means realism, grooming, feature balance, and polish level; do not beautify beyond the target band. "
        "Level lock: match the assigned looksLevelBand exactly; do not upgrade the face; do not change looksLevelBand upward."
        f"{guard}"

    )


def face_to_visual(face: Mapping[str, Any]) -> str:
    face_type = _canonical_face_type(face.get("faceType", "mixed_neutral"))
    parts = [
        face_type_target_visual(face_type),
        _visual(FACE_SHAPE_VISUAL, face.get("faceShape")),
        _visual(EYE_SIZE_VISUAL, face.get("eyeSize")),
        _visual(EYE_TILT_VISUAL, face.get("eyeTilt")),
        _visual(JAWLINE_VISUAL, face.get("jawline")),
        _visual(CHEEK_VISUAL, face.get("cheekFullness")),
        _visual(NOSE_VISUAL, face.get("noseBridge")),
        _visual(LIP_VISUAL, face.get("lipFullness")),
        _visual(BROW_VISUAL, face.get("browThickness")),
        _visual(SKIN_VISUAL, face.get("skinFinish")),
        looks_level_to_visual(float(face.get("looksLevel", 3.0))),
        _visual(VIBE_VISUAL, face.get("vibe")),
    ]
    return _join_nonempty(parts)


def body_to_visual(body: Mapping[str, Any], *, include_internal_weight: bool = False) -> str:
    """Translate body metadata into visible, non-objectifying silhouette language."""
    height = body.get("heightCm")
    height_text = f"height impression around {int(height)}cm" if height else "realistic adult height impression"
    parts = [
        height_text,
        _visual(FRAME_VISUAL, body.get("frame")),
        _visual(BODY_FAT_VISUAL, body.get("bodyFatVisual")),
        _visual(MUSCULARITY_VISUAL, body.get("muscularity")),
        _visual(SHOULDER_VISUAL, body.get("shoulderWidth")),
        _visual(WAIST_VISUAL, body.get("waistDefinition")),
        _visual(HIP_VISUAL, body.get("hipWidth")),
        _visual(LEG_RATIO_VISUAL, body.get("legRatio")),
        _visual(TORSO_VISUAL, body.get("torsoLength")),
        _visual(HEAD_BODY_RATIO_VISUAL, body.get("headBodyRatio")),
        "realistic adult body proportions",
        "natural posture",
    ]
    if include_internal_weight and body.get("weightKgInternal") is not None:
        # Normally not used in prompts. Kept only for debugging.
        parts.append(f"internal metadata weight {body.get('weightKgInternal')}kg")
    return _join_nonempty(parts)


def hair_to_visual(hair: Mapping[str, Any]) -> str:
    parts = [
        _visual(HAIR_LENGTH_VISUAL, hair.get("length")),
        _visual(HAIR_COLOR_VISUAL, hair.get("color")),
        _visual(HAIR_TEXTURE_VISUAL, hair.get("texture")),
    ]
    bangs = _visual(BANGS_VISUAL, hair.get("bangs"))
    base = _join_nonempty(parts)
    if base:
        base = f"{base} hair"
    if bangs and bangs != "no bangs":
        return f"{base} with {bangs}"
    if bangs == "no bangs":
        return f"{base}, no bangs"
    return base


def styling_to_visual(styling: Mapping[str, Any]) -> str:
    return _join_nonempty([
        _visual(MAKEUP_VISUAL, styling.get("makeupLevel")),
        _visual(FASHION_VISUAL, styling.get("fashionMood")),
        _visual(OUTFIT_FIT_VISUAL, styling.get("outfitFit")),
        "campus-appropriate and modest",
    ])


def skin_to_visual(skin: Mapping[str, Any]) -> str:
    tone = _visual(SKIN_TONE_VISUAL, skin.get("tone"), SKIN_TONE_VISUAL["natural_beige"])
    texture = _visual(SKIN_VISUAL, skin.get("texture"), "natural skin texture")
    retouching = str(skin.get("retouching") or "minimal")
    return f"{tone}, {texture}, {retouching} retouching"


def eyewear_prompt_text(accessories: Mapping[str, Any], *, include_none: bool = False) -> str:
    if accessories.get("eyewearGroup") == "glasses":
        eyewear = _visual(EYEWEAR_VISUAL, accessories.get("eyewear"))
        return f"{eyewear}, eyes clearly visible, no lens glare hiding the eyes"
    if include_none:
        return EYEWEAR_VISUAL["none"]
    return ""


def canonical_eyewear_key(accessories: Mapping[str, Any]) -> str:
    if accessories.get("eyewearGroup") == "glasses":
        return str(accessories.get("canonicalEyewear") or accessories.get("eyewear") or "thin_round_metal")
    return "none"


def shot_eyewear_expected(accessories: Mapping[str, Any], shot_type: ShotType) -> str:
    temporary = accessories.get("temporaryEyewearForShot") if isinstance(accessories.get("temporaryEyewearForShot"), Mapping) else {}
    if bool(temporary.get(shot_type)):
        return str(accessories.get("temporaryEyewear") or "thin_round_metal")
    return canonical_eyewear_key(accessories)


def temporary_eyewear_allowed(accessories: Mapping[str, Any], shot_type: ShotType) -> bool:
    temporary = accessories.get("temporaryEyewearForShot") if isinstance(accessories.get("temporaryEyewearForShot"), Mapping) else {}
    return bool(temporary.get(shot_type))


def canonical_eyewear_clause(spec: Mapping[str, Any], shot_type: ShotType) -> str:
    accessories = spec.get("accessories", {}) if isinstance(spec.get("accessories"), Mapping) else {}
    expected = shot_eyewear_expected(accessories, shot_type)
    if expected != "none":
        eyewear = _visual(EYEWEAR_VISUAL, expected)
        exact_eyewear = "clear-frame glasses" if expected == "clear_frame" else eyewear
        fine_frame_lock = ""
        if expected in {"soft_rectangular_metal", "thin_round_metal", "clear_frame"}:
            fine_frame_lock = (
                " v16 required eyewear persistence lock: same-person eyewear consistency is mandatory; "
                "soft or thin frames must remain readable enough that QA can point to frame outline, bridge, and temple arm; "
                "do not let lighting, distance, side angle, activity, or transparent/metal color make required glasses disappear; "
            )
        if shot_type == "face_card":
            return f"wearing the same {exact_eyewear} assigned to this identity, same frame style for this identity, frames visible enough to verify identity consistency, eyes clearly visible, natural lens reflection only"
        if shot_type == "silhouette_card":
            return (
                f"wearing the same {exact_eyewear} from the face_card; preserve the assigned {eyewear}; "
                "frames visible enough to verify identity consistency; do not remove glasses in this shot; "
                f"{fine_frame_lock}"
                "face and eyewear remain readable; do not let full-body framing make glasses unreadable; eyes clearly visible; "
                "v14 silhouette eyewear readability lock: glasses are a required identity feature in this silhouette_card; "
                f"full-body framing must still show the {exact_eyewear}; use a three-quarter crop close enough that the frames are plainly readable; "
                "if the frames would be too small, crop closer rather than removing them; do not approve a no-glasses silhouette for this identity; "
                "front or three-quarter face angle only; avoid rear, far-profile, tiny-face, or backlit crops that hide transparent or metal frames; "
                "for clear-frame or thin metal eyewear, add crisp edge highlights and visible temple arms so QA can read the assigned frame style; "
                "v15 clear-frame silhouette readability lock: transparent frames must have visible lens rims, bridge, and temple arms against the face/background; "
                "choose a readable front or three-quarter upper-body/full-body crop, never a tiny face, pure side profile, shadowed face, or backlit frame that blends away; "
                "clear-frame eyewear is successful only when QA can point to both lenses and at least one temple arm; "
                "not translucent eyewear that disappears into skin tone or background"
            )
        return f"wearing the same {exact_eyewear} from the face_card; preserve the assigned {eyewear}; frames visible enough to verify identity consistency; do not remove glasses in this shot; {fine_frame_lock}face and eyewear remain readable; location or activity must not remove eyewear; environmental context secondary to identity and eyewear consistency; eyes clearly visible, natural lens reflection only"
    if shot_type == "face_card":
        return "natural face, clear unobstructed eyes, natural eye area"
    if shot_type == "silhouette_card":
        return "natural face continuity from the face_card; if the face is visible, keep eyes unobstructed"
    return "natural face continuity from the face_card, clear unobstructed eyes, no added eye accessories"


def eyewear_negative_constraints(spec: Mapping[str, Any], shot_type: ShotType) -> str:
    accessories = spec.get("accessories", {}) if isinstance(spec.get("accessories"), Mapping) else {}
    expected = shot_eyewear_expected(accessories, shot_type)
    if expected != "none":
        constraints = [
            "sunglasses",
            "tinted lenses",
            "lens glare hiding eyes",
            "different frame style",
            "face-covering mask",
        ]
    else:
        constraints = [
            "glasses",
            "eyeglasses",
            "spectacles",
            "sunglasses",
            "tinted lenses",
            "face-covering mask",
        ]
    return "Eyewear-specific avoid: " + "; ".join(constraints) + "."


def environment_to_visual(environment: Mapping[str, Any]) -> str:
    return _join_nonempty([
        _visual(SEASON_VISUAL, environment.get("season")),
        _visual(WEATHER_VISUAL, environment.get("weather")),
        _visual(TIME_OF_DAY_VISUAL, environment.get("timeOfDay")),
        _visual(TEMPERATURE_VISUAL, environment.get("temperatureFeel")),
    ])


def location_scene(spec: Mapping[str, Any], shot_type: Optional[ShotType] = None) -> str:
    location = spec.get("location", {}) if isinstance(spec.get("location"), Mapping) else {}
    location_type = str(location.get("locationType") or "campus_walkway")
    effective_type, entry = _effective_location_type_and_entry(spec, shot_type)
    use_spec_scene = effective_type == location_type
    scene = str(location.get("scene") or entry["scene"]) if use_spec_scene else str(entry["scene"])
    return scene


def _effective_location_type_and_entry(
    spec: Mapping[str, Any],
    shot_type: Optional[ShotType] = None,
) -> Tuple[str, Mapping[str, Any]]:
    location = spec.get("location", {}) if isinstance(spec.get("location"), Mapping) else {}
    location_type = str(location.get("locationType") or "campus_walkway")
    entry = LOCATION_CATALOG.get(location_type, LOCATION_CATALOG["campus_walkway"])
    if shot_type and shot_type not in entry.get("allowedShots", []):
        fallback_type = "campus_cafe" if shot_type == "face_card" else "campus_walkway"
        if shot_type == "vibe_card" and location_type == "small_exhibition":
            fallback_type = "small_exhibition"
        location_type = fallback_type
        entry = LOCATION_CATALOG[fallback_type]
    return location_type, entry


def location_negative_constraints(spec: Mapping[str, Any], shot_type: Optional[ShotType] = None) -> str:
    location_type, entry = _effective_location_type_and_entry(spec, shot_type)
    constraints: List[str] = []
    if entry.get("privacyRisk") == "medium" or entry.get("logoTextRisk") == "medium":
        constraints.extend(LOCATION_MEDIUM_RISK_NEGATIVE_CONSTRAINTS)
    constraints.extend(LOCATION_NEGATIVE_CONSTRAINTS.get(location_type, ()))
    if not constraints:
        return ""
    deduped = list(dict.fromkeys(constraints))
    return "Location-specific avoid: " + "; ".join(deduped) + "."


def _normalize_activity_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _activity_set_for_location(location_type: str) -> set[str]:
    return {_normalize_activity_text(activity) for activity in LOCATION_VIBE_ACTIVITIES.get(location_type, [])}


def vibe_activity_matches_location(location_type: str, activity: Any) -> bool:
    normalized = _normalize_activity_text(activity)
    return bool(normalized and normalized in _activity_set_for_location(location_type))


def sample_vibe_activity_for_location(location_type: str, gender: Gender, rng: random.Random) -> str:
    activities = LOCATION_VIBE_ACTIVITIES.get(str(location_type))
    if activities:
        return _pick(rng, activities)
    return _pick(rng, VIBE_ACTIVITIES[gender])


def normalize_vibe_activity_for_location(
    activity: Any,
    location_type: str,
    gender: Gender,
    rng: random.Random,
) -> str:
    normalized = _normalize_activity_text(activity)
    rewritten = LEGACY_VIBE_ACTIVITY_REWRITES.get(normalized, normalized)
    if vibe_activity_matches_location(location_type, rewritten):
        return rewritten
    if rewritten and location_type not in LOCATION_VIBE_ACTIVITIES and not VIBE_ACTIVITY_LOCATION_PATTERN.search(rewritten):
        return rewritten
    return sample_vibe_activity_for_location(location_type, gender, rng)


def vibe_activity_prompt_text(spec: Mapping[str, Any], gender: Gender) -> str:
    seed = int(spec.get("identitySeed", 0))
    location = spec.get("location", {}) if isinstance(spec.get("location"), Mapping) else {}
    location_type = str(location.get("locationType") or "campus_walkway")
    rng = random.Random(seed + 500)
    normalized = normalize_vibe_activity_for_location(spec.get("vibeActivity"), location_type, gender, rng)
    if vibe_activity_matches_location(location_type, normalized):
        return normalized
    if not VIBE_ACTIVITY_LOCATION_PATTERN.search(normalized):
        return normalized
    clauses = [part.strip() for part in normalized.split(",") if part.strip()]
    kept = [part for part in clauses if not VIBE_ACTIVITY_LOCATION_PATTERN.search(part)]
    if kept:
        return ", ".join(kept)
    return sample_vibe_activity_for_location(location_type, gender, rng)


def fashion_upper_outfit(fashion: Mapping[str, Any]) -> str:
    outerwear = fashion.get("outerwear")
    top = fashion.get("top")
    parts = [str(outerwear) if outerwear else "", str(top) if top else ""]
    return _join_nonempty(parts)


def fashion_full_outfit(fashion: Mapping[str, Any]) -> str:
    return _join_nonempty([
        str(fashion.get("outerwear")) if fashion.get("outerwear") else "",
        str(fashion.get("top")) if fashion.get("top") else "",
        str(fashion.get("bottom")) if fashion.get("bottom") else "",
        str(fashion.get("shoes")) if fashion.get("shoes") else "",
        str(fashion.get("bag")).replace("_", " ") if fashion.get("bag") else "",
    ])


def fashion_to_visual(fashion: Mapping[str, Any], *, full: bool) -> str:
    outfit = fashion_full_outfit(fashion) if full else fashion_upper_outfit(fashion)
    return _join_nonempty([
        outfit,
        _visual(FASHION_VISUAL, fashion.get("category")),
        str(fashion.get("palette") or ""),
        str(fashion.get("material") or ""),
        str(fashion.get("fit") or ""),
        "modest adult campus-appropriate clothing",
    ])


def photo_realism_block(photo: Mapping[str, Any]) -> str:
    realism = _visual(PHOTO_REALISM_VISUAL, photo.get("realismProfile"), PHOTO_REALISM_VISUAL["ordinary_smartphone"])
    return (
        f"{realism}, camera mode {photo.get('cameraMode', 'auto')}, mild natural digital noise, "
        "not a professional photoshoot, slightly imperfect everyday composition, natural skin texture, no heavy beauty filter, "
        "clean but not glossy, not overly sharp commercial photography, authentic campus profile image"
    )


def special_case_note(spec: Mapping[str, Any], shot_type: ShotType) -> str:
    special = spec.get("specialCase", {}) if isinstance(spec.get("specialCase"), Mapping) else {}
    case_type = str(special.get("type") or "none")
    if case_type == "none":
        return ""
    allowed = SPECIAL_CASE_CATALOG.get(case_type, {}).get("allowedShots", [])
    if shot_type not in allowed:
        return ""
    return str(special.get("notes") or SPECIAL_CASE_CATALOG.get(case_type, {}).get("notes") or "")


def subject_block(spec: Mapping[str, Any]) -> str:
    gender = str(spec.get("gender"))
    visual_age = int(spec.get("visualAge", 22))
    adult_label = "adult woman" if gender == "female" else "adult man"
    return (
        f"A realistic adult Korean university student, approximately {visual_age} years old, "
        f"an {adult_label}, natural everyday profile photo, ordinary non-commercial appearance, "
        "authentic campus-based relationship profile style, calm and trustworthy impression."
    )


def broad_face_identity_visual(face_type: Any) -> str:
    canonical = _canonical_face_type(face_type)
    if canonical == "fox_like":
        return "same broad fox_like impression, subtle composed slightly narrow eyes, restrained ordinary face structure, not dog_like warmth, not hamster_like compact round cuteness, not fully mixed_neutral"
    if canonical == "dog_like":
        return "same broad dog_like warm approachable rounded friendly impression and soft ordinary face structure, not long mature horse_like elongation"
    if canonical == "deer_like":
        return "same broad deer_like soft oval and calm gentle impression"
    if canonical == "bear_like":
        return "same broad bear_like grounded warm facial structure"
    if canonical == "cat_like":
        return "same broad cat_like composed almond-eye impression"
    if canonical == "hamster_like":
        return "same broad hamster_like compact rounded adult face impression"
    if canonical == "horse_like":
        return "same broad horse_like longer mature face impression"
    return "same broad balanced mixed_neutral face impression"


def build_silhouette_face_readability_lock(spec: Mapping[str, Any]) -> str:
    """Additional v11 lock for dependent full-body shots where face-type drift was observed."""
    face = spec.get("face", {}) if isinstance(spec.get("face"), Mapping) else {}
    face_type = _canonical_face_type(face.get("faceType", "mixed_neutral"))
    band = str(face.get("looksLevelBand") or looks_level_band(float(face.get("looksLevel", 3.0))))
    parts = [
        "v11 silhouette face readability lock: keep the target faceType cues visible even in the three-quarter/full-body crop",
        "the face should be large and frontal enough for faceType and same-person verification, while body silhouette remains readable",
        "copy the face_card's broad facial structure, looksLevelBand, age, hairstyle, grooming, skin tone, and eyewear state before adapting pose or outfit",
        "do not let distance, posture, outdoor light, face accessories, or outfit create a new sharper/slimmer/higher-band person",
    ]
    if face_type == "hamster_like" and band == "2.5-3.2":
        parts.extend([
            "hamster_like lock: preserve compact rounded adult face and fuller cheeks from the face_card",
            "avoid fox_like narrowness, sharp alert eyes, slimmer jaw, or 3.3-3.8 upgrade",
        ])
    if face_type == "deer_like" and band == "3.3-3.8":
        parts.extend([
            "deer_like lock: preserve soft oval face, calm medium-large eyes, delicate jawline, and gentle quiet expression",
            "avoid collapsing into mixed_neutral because the face is too small or indistinct",
        ])
    if face_type == "cat_like" and band == "3.9-4.3":
        parts.extend([
            "cat_like high-band lock: preserve composed almond-eye lift and neat sharper alert cues",
            "avoid deer_like gentle-soft undershoot while still avoiding celebrity, idol, influencer, or beauty-filter polish",
        ])
    return "; ".join(parts) + "."


def build_identity_consistency_block(spec: Mapping[str, Any], shot_type: ShotType = "vibe_card") -> str:
    face = spec.get("face", {}) if isinstance(spec.get("face"), Mapping) else {}
    hair = spec.get("hair", {}) if isinstance(spec.get("hair"), Mapping) else {}
    skin = spec.get("skin", {}) if isinstance(spec.get("skin"), Mapping) else {}
    accessories = spec.get("accessories", {}) if isinstance(spec.get("accessories"), Mapping) else {}
    face_type = broad_face_identity_visual(face.get("faceType", "mixed_neutral"))
    hair_desc = hair_to_visual(hair)
    skin_desc = _visual(SKIN_TONE_VISUAL, skin.get("tone"), "same natural Korean skin tone")
    eyewear_desc = canonical_eyewear_clause(spec, shot_type)
    if shot_type == "silhouette_card":
        face_guidance = (
            "keep same broad face impression, skin tone, hairstyle, and eyewear if present; "
            "keep identity eyewear state consistent; "
            "face occupies enough pixels to confirm same person; "
            "keep identity-readable facial detail without turning the full-body shot into a close portrait"
        )
    else:
        face_guidance = (
            "canonical face_card same-person lock: use the attached face_card as the authoritative identity anchor; "
            "same broad face-type impression and recognizable facial structure; "
            "same face shape, eye impression, nose-mouth balance, skin tone, hairstyle, hair volume, and grooming; "
            "face visible enough for identity matching, not a distant lifestyle figure"
        )
    if shot_type == "vibe_card" and _canonical_face_type(face.get("faceType", "mixed_neutral")) == "fox_like":
        face_guidance += (
            "; preserve the same subtle fox_like cues from the face_card; keep face visible enough to read the slightly narrow composed eye impression; "
            "avoid over-smiling into dog_like warmth; avoid overly soft cheeks or hamster_like compact cuteness; do not shrink the face too much; "
            "preserve one or two understated fox_like cues even in the lifestyle setting"
        )
    if shot_type == "vibe_card" and _canonical_face_type(face.get("faceType", "mixed_neutral")) == "dog_like":
        face_guidance += (
            "; v15 dog_like vibe identity lock: preserve the face_card's rounded friendly dog_like anchors, soft cheeks, rounder eyes, and soft jawline; "
            "do not elongate into horse_like mature long-face structure; do not replace the canonical dog_like face with a different lifestyle face; "
            "natural candid variation is allowed only after the same dog_like face remains recognizable"
        )
    if shot_type == "vibe_card":
        face_guidance += (
            "; v18 vibe face-type readability lock: do not use a downward-looking or object-first pose; "
            "face angle must remain front-facing or mild three-quarter, with eyes and nose-mouth balance visible; "
            "face-type evidence must be readable enough for QA to verify the target faceType and looksLevelBand; "
            "activity, cup, book, phone, laptop, hands, hair, or gaze must not cover the face or turn the image into an object-focused lifestyle shot"
        )
    return (
        "same person as the canonical portrait, "
        f"{face_guidance}: {face_type}, same {skin_desc}, same {hair_desc}, "
        f"same natural grooming, {eyewear_desc}, preserve the same eyewear or no-eyewear state, same adult visual age, "
        "no beauty upgrade across shots, do not change looksLevelBand upward, no body or face beauty upgrade; "
        "environmental context is secondary to identity, and location or activity must not alter facial identity"
    )


def identity_consistency_block(spec: Mapping[str, Any]) -> str:
    return build_identity_consistency_block(spec, "vibe_card")


# -----------------------------------------------------------------------------
# Prompt builders
# -----------------------------------------------------------------------------


def build_prompt(spec: Mapping[str, Any], shot_type: ShotType, *, _skip_validation: bool = False) -> str:
    """Build the final English prompt for a single shot family."""
    if shot_type not in SHOT_TYPES:
        raise ValueError(f"shot_type must be one of {SHOT_TYPES}")
    normalized = normalize_spec_defaults(spec)
    if not _skip_validation:
        validate_spec(normalized)

    rng = random.Random(int(normalized.get("identitySeed", 0)) + {"face_card": 11, "silhouette_card": 22, "vibe_card": 33}[shot_type])
    shot_spec = apply_safe_special_case_overrides(normalized, shot_type, rng)
    gender: Gender = shot_spec["gender"]  # type: ignore[assignment]
    face = shot_spec["face"]
    body = shot_spec["body"]
    hair = shot_spec["hair"]
    styling = shot_spec["styling"]
    skin = shot_spec["skin"]
    accessories = shot_spec["accessories"]
    environment = shot_spec["environment"]
    fashion = shot_spec["fashion"]
    photo = shot_spec["photo"]
    subject = subject_block(shot_spec)
    hair_desc = hair_to_visual(hair)
    styling_desc = styling_to_visual(styling)
    eyewear_desc = eyewear_prompt_text(accessories)
    eyewear_positive_text = canonical_eyewear_clause(shot_spec, shot_type)
    eyewear_avoid_text = eyewear_negative_constraints(shot_spec, shot_type)
    special_note = special_case_note(shot_spec, shot_type)

    vibe_activity = vibe_activity_prompt_text(shot_spec, gender)
    vibe_location = location_scene(shot_spec, "vibe_card")
    location_text = location_scene(shot_spec, shot_type)
    location_avoid_text = location_negative_constraints(shot_spec, shot_type)
    vibe_location_avoid_text = location_negative_constraints(shot_spec, "vibe_card")
    season_text = environment_to_visual(environment)
    realism_text = photo_realism_block(photo)
    face_target_text = build_face_type_target_block(shot_spec, shot_type)
    looks_target_text = build_looks_level_target_block(shot_spec, shot_type)
    face_card_depolish_text = build_face_card_depolish_block(shot_spec)
    targeting_version_text = f"Prompt targeting version: {PROMPT_TARGETING_VERSION}."

    if shot_type == "face_card":
        eyewear_line = f"\nEyewear consistency:\n{eyewear_positive_text}.\n"
        special_line = f"\nSpecial safe variation:\n{special_note}.\n" if special_note else ""
        return f"""
{subject}

Target metadata:
{targeting_version_text}
{face_target_text}
{looks_target_text}

Anti-overbeautification and face-card camera calibration:
{face_card_depolish_text}

Face details:
{face_to_visual(face)}, {skin_to_visual(skin)}.
{eyewear_line}
Hair and grooming:
{hair_desc}, {styling_desc}.

Upper outfit only:
{fashion_to_visual(fashion, full=False)}. Keep the crop above the waist; lower garments are outside the frame.

Composition:
head-and-shoulders portrait, face clearly visible, {photo.get("gaze")}, natural relaxed expression, simple warm off-white or campus-neutral background, face remains readable.
{special_line}
Lighting and camera:
{_visual(TIME_OF_DAY_VISUAL, environment.get("timeOfDay"))}, {realism_text}.

Rules:
one image only, no text in image, no watermark, no visible logo, adult Korean university student, realistic, calm, trustworthy, ordinary campus profile image.

{COMMON_NEGATIVE}
{eyewear_avoid_text}
{location_avoid_text}
""".strip()

    if shot_type == "silhouette_card":
        eyewear_line = f" {eyewear_positive_text}."
        special_line = f"\nSpecial safe variation:\n{special_note}.\n" if special_note else ""
        silhouette_identity_rule = (
            "show three-quarter body or full body, but keep the face clearly visible and identity-readable; "
            "use a front-facing or mild three-quarter face angle, not a strict side profile; "
            "keep the face large enough to recognize the same person from the face_card; "
            "body proportions remain readable, but identity consistency is still required; "
            "do not use strict side-profile; do not use far-distance full-body shot; "
            "avoid back view; avoid face turned too far away; avoid tiny face; "
            "avoid face hidden by hair, scarf, hat, hand, phone, bag, or shadow; "
            "avoid extreme distance from camera or environmental shot where body is readable but face is too small"
        )
        silhouette_readability_lock = build_silhouette_face_readability_lock(shot_spec)
        return f"""
{subject}

Target metadata:
{targeting_version_text}
{face_target_text}
{looks_target_text}
{silhouette_readability_lock}

Identity consistency:
{build_identity_consistency_block(shot_spec, "silhouette_card")}.

Body and silhouette:
{body_to_visual(body)}. Full outfit shows the overall silhouette with modest coverage and no body-focused styling, bottom visible: {bool(fashion.get("bottomVisible"))}, silhouette readable: {bool(fashion.get("silhouetteReadable"))}.{eyewear_line}

Eyewear consistency:
{eyewear_positive_text}.

Full outfit:
{fashion_to_visual(fashion, full=True)}.

Season and environment:
{season_text}.

Composition:
use the existing face_card as the identity reference, three-quarter body or full-body photo, {photo.get("pose")}, {silhouette_identity_rule}, body proportions readable, no oversized padding, no heavy winter coat hiding body shape, no extreme wide-angle distortion, camera at chest height, enough space around the body, avoid waist-up portrait, avoid head-and-shoulders crop, avoid close-up crop, avoid face-only framing, face and posture remain learnable.

Location:
{location_text}.
{special_line}
Lighting and camera:
{realism_text}.

Rules:
one image only, exactly one adult subject, no text in image, no watermark, no visible logo, no crowd-focused background, adult Korean university student, readable modest outfit, authentic campus profile image. If outerwear is present, keep it light enough that the body silhouette remains readable.

{COMMON_NEGATIVE}
{eyewear_avoid_text}
{location_avoid_text}
""".strip()

    # vibe_card
    eyewear_line = f"\nEyewear consistency:\n{eyewear_positive_text}.\n"
    special_line = f"\nSpecial safe variation:\n{special_note}.\n" if special_note else ""
    return f"""
{subject}

Target metadata:
{targeting_version_text}
{looks_target_text}

Identity consistency:
{build_identity_consistency_block(shot_spec, "vibe_card")}.
{eyewear_line}
Season and setting:
{season_text}.

Mood and lifestyle:
{vibe_activity}, {_visual(FASHION_VISUAL, fashion.get("category"))}, calm, sincere, trust-based campus relationship platform mood, quiet everyday activity, face recognizable.

Composition:
half-body or environmental portrait, {photo.get("pose")}, relaxed shoulders, gentle expression, front-facing or mild three-quarter face angle, no strict side profile, no back view, no face hidden by props, hair, hands, phone, bag, or shadow, face occupies enough pixels to compare with the face_card, environmental context stays secondary to identity consistency.

Location:
{vibe_location}.
{special_line}
Lighting and camera:
{realism_text}.

Rules:
one image only, exactly one adult subject clearly visible, adult Korean university student, realistic, calm, trustworthy, ordinary campus profile image. Keep the person as the main subject, not the place or object. Use the activity as a natural everyday moment with a sincere, unstaged social profile feel. The background may show context, but it stays subtle, uncluttered, and non-identifying. Preserve the same person from the face_card reference, including broad face impression, face shape, eye impression, nose-mouth balance, skin tone, general hairstyle, hair volume, grooming, and eyewear when present or no-eyewear when absent. Do not let location, activity, expression, gaze, or pose create a different facial identity. Do not beautify beyond the target looksLevelBand.

{COMMON_NEGATIVE}
{eyewear_avoid_text}
Vibe-card avoid: visible logo; brand logo; readable signs; readable text; watermark; influencer pose; crowd-focused background; extra people as subjects.
{vibe_location_avoid_text}
""".strip()


def build_asset_record(spec: Mapping[str, Any], shot_type: ShotType) -> Dict[str, Any]:
    normalized = normalize_spec_defaults(spec)
    profile_id = str(normalized["profileId"])
    paths = storage_paths(profile_id, shot_type)
    metadata = identity_metadata_summary(normalized)
    fashion = normalized["fashion"]
    accessories = normalized["accessories"]
    expected_eyewear = shot_eyewear_expected(accessories, shot_type)
    temporary_allowed = temporary_eyewear_allowed(accessories, shot_type)
    prompt = build_prompt(normalized, shot_type)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "promptBuilderVersion": PROMPT_BUILDER_VERSION,
        "promptTargetingVersion": PROMPT_TARGETING_VERSION,
        "metadataVersion": METADATA_VERSION,
        "profileId": profile_id,
        "assetId": f"{profile_id}__{shot_type}__v001",
        "gender": normalized["gender"],
        "shotType": shot_type,
        "legacyStoragePath": paths["legacy"],
        "storagePath": paths["storagePath"],
        "prompt": prompt,
        "promptHash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:24],
        "negative": COMMON_NEGATIVE,
        "metadata": normalized,
        "skinTone": metadata["skinTone"],
        "skinTexture": metadata["skinTexture"],
        "eyewear": metadata["eyewear"],
        "eyewearGroup": metadata["eyewearGroup"],
        "hasEyewear": metadata["hasEyewear"],
        "canonicalEyewear": metadata["canonicalEyewear"],
        "eyewearConsistencyPolicy": metadata["eyewearConsistencyPolicy"],
        "shotEyewearExpected": expected_eyewear,
        "temporaryEyewearAllowed": temporary_allowed,
        "temporaryEyewearApplied": temporary_allowed,
        "targetHasEyewear": bool(expected_eyewear != "none"),
        "targetEyewearGroup": "glasses" if expected_eyewear != "none" else "none",
        "targetEyewear": expected_eyewear,
        "targetCanonicalEyewear": metadata["canonicalEyewear"],
        "targetShotEyewearExpected": expected_eyewear,
        "season": metadata["season"],
        "weather": metadata["weather"],
        "timeOfDay": metadata["timeOfDay"],
        "locationType": metadata["locationType"],
        "fashionCategory": metadata["fashionCategory"],
        "fashionPalette": metadata["fashionPalette"],
        "specialCase": metadata["specialCase"],
        "bottomVisible": bool(fashion.get("bottomVisible")),
        "silhouetteReadable": bool(fashion.get("silhouetteReadable")),
        "faceType": metadata["faceType"],
        "looksLevel": metadata["looksLevel"],
        "looksLevelBand": metadata["looksLevelBand"],
        "targetFaceType": metadata["faceType"],
        "targetLooksLevel": metadata["looksLevel"],
        "targetLooksLevelBand": metadata["looksLevelBand"],
        "qaChecklist": QA_CHECKLIST,
    }


def build_asset_records(spec: Mapping[str, Any], shot_types: Sequence[ShotType] = SHOT_TYPES) -> List[Dict[str, Any]]:
    return [build_asset_record(spec, shot_type) for shot_type in shot_types]


def make_rec_event_context(asset_record: Mapping[str, Any]) -> Dict[str, Any]:
    """Context payload to store in recEvents when a user reacts to an AI profile card."""
    return {
        "surface": "ai_preference_onboarding",
        "targetType": "ai_profile",
        "assetId": asset_record["assetId"],
        "shotType": asset_record["shotType"],
        "metadataVersion": str(asset_record.get("metadataVersion") or METADATA_VERSION),
        "storagePath": asset_record["storagePath"],
        "legacyStoragePath": asset_record["legacyStoragePath"],
    }


# -----------------------------------------------------------------------------
# Spec generation
# -----------------------------------------------------------------------------


def _looks_level(rng: random.Random) -> float:
    bucket = rng.random()
    if bucket < 0.15:
        return round(rng.uniform(1.7, 2.4), 1)
    if bucket < 0.60:
        return round(rng.uniform(2.5, 3.2), 1)
    if bucket < 0.90:
        return round(rng.uniform(3.3, 3.8), 1)
    return round(rng.uniform(3.9, 4.2), 1)


def _face_shape_for(face_type: str, rng: random.Random) -> str:
    face_type = _canonical_face_type(face_type)
    options = {
        "cat_like": ["soft_oval", "balanced", "heart"],
        "dog_like": ["round", "soft_oval", "balanced"],
        "hamster_like": ["round", "soft_oval"],
        "bear_like": ["soft_rectangular", "balanced", "round"],
        "fox_like": ["slightly_long", "soft_oval", "heart"],
        "deer_like": ["soft_oval", "slightly_long", "balanced"],
        "horse_like": ["slightly_long", "soft_rectangular"],
        "mixed_neutral": ["balanced", "soft_oval", "soft_rectangular"],
    }
    return _pick(rng, options.get(face_type, options["mixed_neutral"]))


def _eye_size_for(face_type: str, rng: random.Random) -> str:
    face_type = _canonical_face_type(face_type)
    options = {
        "cat_like": ["medium", "narrow_medium", "medium_large"],
        "dog_like": ["round_medium", "medium_large", "medium"],
        "hamster_like": ["round_medium", "medium"],
        "bear_like": ["medium", "round_medium"],
        "fox_like": ["narrow_medium", "medium"],
        "deer_like": ["medium_large", "medium"],
        "horse_like": ["medium", "small_medium"],
        "mixed_neutral": ["medium", "round_medium", "small_medium"],
    }
    return _pick(rng, options.get(face_type, options["mixed_neutral"]))


def _eye_tilt_for(face_type: str, rng: random.Random) -> str:
    face_type = _canonical_face_type(face_type)
    options = {
        "cat_like": ["slightly_lifted", "neutral"],
        "dog_like": ["neutral", "soft_downturned"],
        "hamster_like": ["neutral", "soft_downturned"],
        "bear_like": ["neutral", "soft_downturned"],
        "fox_like": ["slightly_lifted", "neutral"],
        "deer_like": ["neutral_slight_downturned", "neutral"],
        "horse_like": ["neutral", "neutral_slight_downturned"],
        "mixed_neutral": ["neutral", "neutral_slight_downturned", "slightly_lifted"],
    }
    return _pick(rng, options.get(face_type, options["mixed_neutral"]))


def sample_face_spec(gender: Gender, rng: random.Random) -> Dict[str, Any]:
    face_type = _canonical_face_type(_pick_weighted(rng, FACE_TYPE_WEIGHTS))
    looks_level = _looks_level(rng)
    vibe_options = [
        "soft",
        "calm",
        "warm",
        "intellectual",
        "clear_trust",
        "quiet_romance",
    ]
    if face_type in {"cat_like", "fox_like"}:
        vibe_options.extend(["chic", "calm_intellectual"])
    if face_type in {"dog_like", "bear_like"}:
        vibe_options.extend(["warm_sporty", "warm"])
    return {
        "faceType": face_type,
        "looksLevel": looks_level,
        "looksLevelBand": looks_level_band(looks_level),
        "faceShape": _face_shape_for(face_type, rng),
        "eyeSize": _eye_size_for(face_type, rng),
        "eyeTilt": _eye_tilt_for(face_type, rng),
        "jawline": _pick(rng, ["soft", "soft_defined", "defined", "rounded", "slightly_angular"]),
        "cheekFullness": _pick(rng, ["low", "moderate", "full", "defined"]),
        "noseBridge": _pick(rng, ["soft_low", "soft_medium", "medium", "high_medium"]),
        "lipFullness": _pick(rng, ["thin_natural", "natural_medium", "soft_full"]),
        "browThickness": _pick(rng, ["light_natural", "natural", "straight_natural", "thick_natural"]),
        "skinFinish": _pick(rng, ["natural", "natural_clear", "healthy", "slightly_textured"]),
        "vibe": _pick(rng, vibe_options),
    }


def sample_body_spec(gender: Gender, rng: random.Random) -> Dict[str, Any]:
    if gender == "female":
        height = int(round(rng.triangular(155, 174, 163)))
        body_visual = _pick(rng, ["slim", "soft_slim", "healthy_average", "average_soft", "fit_natural"])
        frame = _pick(rng, ["small", "small_medium", "medium"])
        muscularity = _pick(rng, ["low_natural", "natural", "moderate_natural"])
        shoulder = _pick(rng, ["narrow", "narrow_medium", "medium"])
        waist = _pick(rng, ["straight", "soft_defined", "defined", "not_emphasized"])
        hip = _pick(rng, ["narrow", "medium", "soft_medium"])
        weight = int(round(rng.triangular(45, 64, 52)))
    else:
        height = int(round(rng.triangular(168, 188, 176)))
        body_visual = _pick(rng, ["healthy_average", "solid_average", "fit_natural", "athletic_natural"])
        frame = _pick(rng, ["medium", "medium_broad", "broad"])
        muscularity = _pick(rng, ["natural", "moderate_natural", "athletic_moderate"])
        shoulder = _pick(rng, ["medium", "medium_broad", "broad"])
        waist = _pick(rng, ["straight", "not_emphasized", "soft_defined"])
        hip = _pick(rng, ["not_emphasized", "medium"])
        weight = int(round(rng.triangular(58, 84, 70)))

    return {
        "heightCm": height,
        "weightKgInternal": weight,
        "bodyFatVisual": body_visual,
        "frame": frame,
        "muscularity": muscularity,
        "shoulderWidth": shoulder,
        "waistDefinition": waist,
        "hipWidth": hip,
        "legRatio": _pick(rng, ["balanced", "slightly_long", "long"]),
        "torsoLength": _pick(rng, ["short_balanced", "balanced", "slightly_long"]),
        "headBodyRatio": _pick(rng, ["realistic", "balanced", "slightly_small_head"]),
    }


def sample_hair_spec(gender: Gender, rng: random.Random) -> Dict[str, Any]:
    if gender == "female":
        return {
            "length": _pick(rng, ["medium", "medium_long", "long", "bob"]),
            "texture": _pick(rng, ["soft_straight", "natural_straight", "slightly_wavy", "soft_wavy"]),
            "color": _pick(rng, ["natural_black", "natural_dark_brown", "dark_brown"]),
            "bangs": _pick(rng, ["none", "side_bangs", "see_through_bangs"]),
        }
    return {
        "length": _pick(rng, ["short", "medium"]),
        "texture": _pick(rng, ["natural_straight", "soft_straight", "textured", "slightly_wavy"]),
        "color": _pick(rng, ["natural_black", "natural_dark_brown", "dark_brown"]),
        "bangs": _pick(rng, ["none", "soft_fringe"]),
    }


def sample_styling_spec(gender: Gender, rng: random.Random) -> Dict[str, Any]:
    if gender == "female":
        makeup = _pick(rng, ["light_natural", "natural"])
        fashion = _pick(rng, ["campus_neat", "campus_casual", "minimal_clean", "soft_romantic", "intellectual_neat"])
    else:
        makeup = "clean_grooming"
        fashion = _pick(rng, ["campus_casual", "minimal_clean", "sporty_casual", "intellectual_neat", "campus_neat"])
    return {
        "makeupLevel": makeup,
        "fashionMood": fashion,
        "outfitFit": _pick(rng, ["regular_fit", "relaxed_fit", "neat_regular", "slim_regular"]),
        "avoidSexualizedStyling": True,
    }


def sample_skin_spec(gender: Gender, rng: random.Random) -> Dict[str, Any]:
    _ = gender
    return {
        "tone": _pick(rng, list(SKIN_TONE_VISUAL.keys())),
        "texture": _pick(rng, ["natural", "natural_clear", "healthy", "slightly_textured"]),
        "retouching": "minimal",
    }


def sample_accessory_spec(gender: Gender, rng: random.Random, eyewear_group: Optional[str] = None) -> Dict[str, Any]:
    if eyewear_group is None:
        ratio = 0.10 if gender == "female" else 0.20
        eyewear_group = "glasses" if rng.random() < ratio else "none"
    if eyewear_group not in {"none", "glasses"}:
        raise ValueError("eyewear_group must be none, glasses, or None")
    eyewear = "none" if eyewear_group == "none" else _pick(rng, [key for key in EYEWEAR_VISUAL.keys() if key != "none"])
    return {
        "eyewear": eyewear,
        "eyewearGroup": eyewear_group,
        "hasEyewear": eyewear_group == "glasses",
        "canonicalEyewear": eyewear,
        "eyewearConsistencyPolicy": "same_across_all_shots",
        "temporaryEyewearForShot": {},
        "temporaryEyewearAllowed": False,
        "temporaryEyewearApplied": False,
        "hat": _pick(rng, ["none", "none", "none", "simple_cap", "beanie"]),
        "bag": _pick(rng, ["canvas_tote", "backpack", "shoulder_bag", "none"]),
        "jewelry": _pick(rng, ["none", "none", "minimal_silver", "simple_watch"]),
    }


def sample_environment_spec(gender: Gender, rng: random.Random) -> Dict[str, Any]:
    _ = gender
    season = _pick(rng, ["spring", "summer", "autumn", "winter"])
    weather = _weather_for_season(season, rng)
    time_options = ["daylight", "golden_hour", "early_evening"]
    return {
        "season": season,
        "weather": weather,
        "timeOfDay": _pick(rng, time_options),
        "temperatureFeel": _temperature_for_season(season, weather),
    }


def _environment_for_season(season: str, rng: random.Random) -> Dict[str, Any]:
    weather = _weather_for_season(season, rng)
    return {
        "season": season,
        "weather": weather,
        "timeOfDay": _pick(rng, ["daylight", "golden_hour", "early_evening"]),
        "temperatureFeel": _temperature_for_season(season, weather),
    }


def _pick_location_candidate(
    rng: random.Random,
    candidates: Sequence[Tuple[str, Mapping[str, Any]]],
    shot_type: Optional[ShotType],
) -> Tuple[str, Mapping[str, Any]]:
    if shot_type == "vibe_card":
        keys = [location_type for location_type, _ in candidates]
        weights = [float(VIBE_LOCATION_WEIGHTS.get(location_type, 1.0)) for location_type in keys]
        selected = rng.choices(list(range(len(candidates))), weights=weights, k=1)[0]
        return candidates[selected]
    return candidates[rng.randrange(len(candidates))]


def sample_location_spec(gender: Gender, rng: random.Random, shot_type: Optional[ShotType] = None) -> Dict[str, Any]:
    _ = gender
    candidates = [
        (location_type, entry)
        for location_type, entry in LOCATION_CATALOG.items()
        if shot_type is None or shot_type in entry.get("allowedShots", [])
    ]
    if not candidates:
        candidates = [("campus_walkway", LOCATION_CATALOG["campus_walkway"])]
    location_type, entry = _pick_location_candidate(rng, candidates, shot_type)
    return {
        "locationType": location_type,
        "scene": entry["scene"],
        "privacyRisk": entry["privacyRisk"],
        "logoTextRisk": entry["logoTextRisk"],
        "allowedShots": list(entry["allowedShots"]),
    }


def _sample_location_for_season(
    gender: Gender,
    rng: random.Random,
    *,
    season: str,
    shot_type: Optional[ShotType] = None,
) -> Dict[str, Any]:
    _ = gender
    candidates = [
        (location_type, entry)
        for location_type, entry in LOCATION_CATALOG.items()
        if (shot_type is None or shot_type in entry.get("allowedShots", []))
        and season in entry.get("seasonCompatibility", [])
    ]
    if not candidates:
        return sample_location_spec(gender, rng, shot_type)
    location_type, entry = _pick_location_candidate(rng, candidates, shot_type)
    return {
        "locationType": location_type,
        "scene": entry["scene"],
        "privacyRisk": entry["privacyRisk"],
        "logoTextRisk": entry["logoTextRisk"],
        "allowedShots": list(entry["allowedShots"]),
    }


def _seasonal_outerwear(category: Mapping[str, Any], season: str, rng: random.Random) -> Optional[str]:
    seasonal = category.get("outerwear") if isinstance(category.get("outerwear"), Mapping) else {}
    options = seasonal.get(season) if isinstance(seasonal, Mapping) else None
    if not options:
        options = [None]
    return _pick(rng, list(options))  # type: ignore[arg-type]


def sample_fashion_spec(
    gender: Gender,
    rng: random.Random,
    season: Optional[str] = None,
    shot_type: Optional[ShotType] = None,
) -> Dict[str, Any]:
    _ = shot_type
    season = season or _pick(rng, ["spring", "summer", "autumn", "winter"])
    categories = SAFE_FASHION_CATALOG[gender]
    category = _pick(rng, list(categories.keys()))
    config = categories[category]
    outerwear = _seasonal_outerwear(config, season, rng)
    bag = _pick(rng, config["bags"])
    return {
        "category": category,
        "palette": _pick(rng, config["palettes"]),
        "outerwear": outerwear,
        "top": _pick(rng, config["tops"]),
        "bottom": _pick(rng, config["bottoms"]),
        "shoes": _pick(rng, config["shoes"]),
        "bag": bag,
        "fit": config["fit"],
        "material": config["material"],
        "bottomVisible": bool(config["bottomVisible"]),
        "silhouetteReadable": bool(config["silhouetteReadable"]),
        "modest": True,
    }


def sample_photo_spec(gender: Gender, rng: random.Random, shot_type: Optional[ShotType] = None) -> Dict[str, Any]:
    _ = gender
    pose_by_shot = {
        "face_card": ["relaxed head-and-shoulders pose", "natural slight three-quarter face pose"],
        "silhouette_card": ["standing naturally", "walking slowly with readable posture"],
        "vibe_card": ["naturally engaged in a quiet campus activity", "relaxed environmental portrait pose"],
    }
    gaze_by_shot = {
        "face_card": ["looking near the camera", "gentle direct gaze"],
        "silhouette_card": ["looking naturally forward", "soft gaze near camera"],
        "vibe_card": ["face recognizable with relaxed gaze", "looking naturally toward the activity"],
    }
    crop_by_shot = {
        "face_card": ["head-and-shoulders crop"],
        "silhouette_card": ["three-quarter body or full-body crop"],
        "vibe_card": ["half-body or environmental portrait crop"],
    }
    key = shot_type or "face_card"
    return {
        "realismProfile": _pick(rng, list(PHOTO_REALISM_VISUAL.keys())),
        "cameraMode": "auto",
        "imperfectionLevel": "mild",
        "pose": _pick(rng, pose_by_shot.get(key, pose_by_shot["face_card"])),
        "gaze": _pick(rng, gaze_by_shot.get(key, gaze_by_shot["face_card"])),
        "crop": _pick(rng, crop_by_shot.get(key, crop_by_shot["face_card"])),
    }


def sample_special_case_spec(gender: Gender, rng: random.Random, season: Optional[str] = None) -> Dict[str, Any]:
    _ = gender
    weighted = {key: float(value["ratioWeight"]) for key, value in SPECIAL_CASE_CATALOG.items()}
    case_type = _pick_weighted(rng, weighted)
    if season != "winter" and case_type == "snowy_walk":
        case_type = "none"
    entry = SPECIAL_CASE_CATALOG[case_type]
    return {
        "type": case_type,
        "allowed": bool(entry["allowed"]),
        "bottomVisibleOverride": entry["bottomVisibleOverride"],
        "notes": entry["notes"],
    }


def apply_safe_special_case_overrides(spec: Mapping[str, Any], shot_type: ShotType, rng: random.Random) -> Dict[str, Any]:
    out = normalize_spec_defaults(spec)
    special = out.get("specialCase", {}) if isinstance(out.get("specialCase"), Mapping) else {}
    case_type = str(special.get("type") or "none")
    if case_type == "none":
        return out
    entry = SPECIAL_CASE_CATALOG.get(case_type)
    if not entry or shot_type not in entry.get("allowedShots", []):
        return out
    out["specialCase"] = {**dict(special), "allowed": True, "notes": special.get("notes") or entry.get("notes")}
    fashion = dict(out.get("fashion", {}))
    if entry.get("bottomVisibleOverride") is not None:
        fashion["bottomVisible"] = bool(entry["bottomVisibleOverride"])
    if case_type == "snowy_walk":
        out["environment"] = _environment_for_season("winter", rng)
        fashion["silhouetteReadable"] = True
    if case_type == "exhibition_visit":
        out["location"] = sample_location_spec(str(out["gender"]), rng, "vibe_card")  # type: ignore[arg-type]
        out["location"]["locationType"] = "small_exhibition"
        out["location"]["scene"] = LOCATION_CATALOG["small_exhibition"]["scene"]
        out["vibeActivity"] = sample_vibe_activity_for_location("small_exhibition", str(out["gender"]), rng)  # type: ignore[arg-type]
        out["vibeLocation"] = out["location"]["scene"]
    if case_type == "campus_sports_after_activity":
        out["location"] = dict(LOCATION_CATALOG["campus_sports_court"])
        out["location"]["locationType"] = "campus_sports_court"
        out["vibeActivity"] = sample_vibe_activity_for_location("campus_sports_court", str(out["gender"]), rng)  # type: ignore[arg-type]
        out["vibeLocation"] = out["location"]["scene"]
    out["fashion"] = fashion
    return out


def sample_spec(gender: Gender, numeric_id: int, *, seed: Optional[int] = None, id_width: int = 3) -> Dict[str, Any]:
    if gender not in GENDERS:
        raise ValueError(f"gender must be one of {GENDERS}")
    identity_seed = int(seed if seed is not None else (10_000 if gender == "female" else 20_000) + int(numeric_id))
    rng = random.Random(identity_seed)
    profile_id = make_profile_id(gender, numeric_id, width=id_width)
    visual_age = int(rng.triangular(20, 25, 22))
    if visual_age < 20:
        visual_age = 20

    face = sample_face_spec(gender, rng)
    body = sample_body_spec(gender, rng)
    hair = sample_hair_spec(gender, rng)
    styling = sample_styling_spec(gender, rng)
    skin = sample_skin_spec(gender, rng)
    accessories = sample_accessory_spec(gender, rng)
    environment = sample_environment_spec(gender, rng)
    location = _sample_location_for_season(gender, rng, season=environment["season"], shot_type="vibe_card")
    fashion = sample_fashion_spec(gender, rng, season=environment["season"])
    photo = sample_photo_spec(gender, rng)
    special_case = sample_special_case_spec(gender, rng, season=environment["season"])

    vibe_activity = sample_vibe_activity_for_location(str(location["locationType"]), gender, rng)

    spec: Dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "promptBuilderVersion": PROMPT_BUILDER_VERSION,
        "promptTargetingVersion": PROMPT_TARGETING_VERSION,
        "metadataVersion": METADATA_VERSION,
        "profileId": profile_id,
        "gender": gender,
        "visualAge": visual_age,
        "identitySeed": identity_seed,
        "isSynthetic": True,
        "face": face,
        "body": body,
        "hair": hair,
        "styling": styling,
        "skin": skin,
        "accessories": accessories,
        "environment": environment,
        "location": location,
        "fashion": fashion,
        "photo": photo,
        "specialCase": special_case,
        "shotOutfits": {
            "faceCard": fashion_upper_outfit(fashion) or _pick(rng, FACE_CARD_OUTFITS[gender]),
            "fullBody": fashion_full_outfit(fashion) or _pick(rng, FULL_BODY_OUTFITS[gender]),
        },
        "vibeActivity": vibe_activity,
        "vibeLocation": location["scene"],
        "storagePaths": storage_paths(profile_id),
        "shotPlan": [
            {"shotType": shot_type, "storagePath": storage_paths(profile_id, shot_type)["storagePath"]}
            for shot_type in SHOT_TYPES
        ],
        "qa": {
            "adultVisual": None,
            "campusRealism": None,
            "noSchoolUniform": None,
            "noRevealingClothes": None,
            "noInfluencerPhotoshoot": None,
            "identityConsistentAcrossShots": None,
            "approved": None,
        },
    }
    spec["metadata"] = identity_metadata_summary(spec)
    validate_spec(spec)
    return spec


def identity_metadata_summary(spec: Mapping[str, Any]) -> Dict[str, Any]:
    face = spec.get("face", {}) if isinstance(spec.get("face"), Mapping) else {}
    skin = spec.get("skin", {}) if isinstance(spec.get("skin"), Mapping) else {}
    accessories = spec.get("accessories", {}) if isinstance(spec.get("accessories"), Mapping) else {}
    environment = spec.get("environment", {}) if isinstance(spec.get("environment"), Mapping) else {}
    location = spec.get("location", {}) if isinstance(spec.get("location"), Mapping) else {}
    fashion = spec.get("fashion", {}) if isinstance(spec.get("fashion"), Mapping) else {}
    special = spec.get("specialCase", {}) if isinstance(spec.get("specialCase"), Mapping) else {}
    return {
        "promptBuilderVersion": PROMPT_BUILDER_VERSION,
        "promptTargetingVersion": PROMPT_TARGETING_VERSION,
        "metadataVersion": METADATA_VERSION,
        "faceType": _canonical_face_type(face.get("faceType")),
        "looksLevel": float(face.get("looksLevel", 3.0)),
        "looksLevelBand": str(face.get("looksLevelBand") or looks_level_band(face.get("looksLevel", 3.0))),
        "skinTone": skin.get("tone"),
        "skinTexture": skin.get("texture"),
        "eyewear": accessories.get("eyewear"),
        "eyewearGroup": accessories.get("eyewearGroup"),
        "hasEyewear": bool(accessories.get("hasEyewear")),
        "canonicalEyewear": canonical_eyewear_key(accessories),
        "eyewearConsistencyPolicy": accessories.get("eyewearConsistencyPolicy"),
        "temporaryEyewearAllowed": bool(accessories.get("temporaryEyewearAllowed")),
        "temporaryEyewearApplied": bool(accessories.get("temporaryEyewearApplied")),
        "season": environment.get("season"),
        "weather": environment.get("weather"),
        "timeOfDay": environment.get("timeOfDay"),
        "locationType": location.get("locationType"),
        "fashionCategory": fashion.get("category"),
        "fashionPalette": fashion.get("palette"),
        "specialCase": special.get("type"),
        "bottomVisible": bool(fashion.get("bottomVisible")),
        "silhouetteReadable": bool(fashion.get("silhouetteReadable")),
    }


def _sync_metadata(spec: Dict[str, Any]) -> Dict[str, Any]:
    face = spec.get("face") if isinstance(spec.get("face"), Mapping) else {}
    if isinstance(face, Mapping):
        face_out = dict(face)
        face_out["faceType"] = _canonical_face_type(face_out.get("faceType"))
        face_out["looksLevelBand"] = str(face_out.get("looksLevelBand") or looks_level_band(face_out.get("looksLevel", 3.0)))
        spec["face"] = face_out
    spec["metadata"] = identity_metadata_summary(spec)
    return spec


def _sample_looks_level_in_band(band: str, rng: random.Random) -> float:
    if band == "4.4-5.0":
        raise ValueError("looksLevelBand 4.4-5.0 is blocked for final prompt specs")
    low, high = LOOKS_LEVEL_BAND_RANGES[band]
    return round(rng.uniform(low, high), 1)


def assign_face_type_groups_for_batch(
    specs: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Any],
    seed: int,
) -> List[Dict[str, Any]]:
    out = [normalize_spec_defaults(spec) for spec in specs]
    for gender in GENDERS:
        indexed = [(index, spec) for index, spec in enumerate(out) if spec.get("gender") == gender]
        indexed.sort(key=lambda pair: _profile_sort_key(pair[1]))
        counts = _gender_target_counts(targets, gender, len(indexed), FACE_TYPE_ORDER)
        sequence = _spread_values_by_counts(counts, FACE_TYPE_ORDER, seed=int(seed) + (0 if gender == "female" else 10_000))
        for offset, ((index, spec), face_type) in enumerate(zip(indexed, sequence)):
            rng = random.Random(int(seed) + int(spec.get("identitySeed", 0)) + offset * 97)
            face = dict(spec["face"])
            face["faceType"] = _canonical_face_type(face_type)
            face["faceShape"] = _face_shape_for(face_type, rng)
            face["eyeSize"] = _eye_size_for(face_type, rng)
            face["eyeTilt"] = _eye_tilt_for(face_type, rng)
            out[index]["face"] = face
            _sync_metadata(out[index])
    return out


def assign_looks_level_bands_for_batch(
    specs: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Any],
    seed: int,
) -> List[Dict[str, Any]]:
    out = [normalize_spec_defaults(spec) for spec in specs]
    for gender in GENDERS:
        indexed = [(index, spec) for index, spec in enumerate(out) if spec.get("gender") == gender]
        indexed.sort(key=lambda pair: _profile_sort_key(pair[1]))
        counts = _gender_target_counts(targets, gender, len(indexed), LOOKS_LEVEL_BANDS)
        if counts.get("4.4-5.0", 0):
            raise ValueError("Exact looksLevelBand assignment cannot include 4.4-5.0")
        sequence = _spread_values_by_counts(counts, LOOKS_LEVEL_BANDS, seed=int(seed) + (1_000 if gender == "female" else 11_000))
        for offset, ((index, spec), band) in enumerate(zip(indexed, sequence)):
            rng = random.Random(int(seed) + int(spec.get("identitySeed", 0)) + offset * 193)
            face = dict(spec["face"])
            face["looksLevelBand"] = band
            face["looksLevel"] = _sample_looks_level_in_band(band, rng)
            out[index]["face"] = face
            _sync_metadata(out[index])
    return out


def _balanced_eyewear_indices(indexed: Sequence[Tuple[int, Dict[str, Any]]], count: int, seed: int) -> set[int]:
    if count <= 0:
        return set()
    groups: Dict[Tuple[str, str], List[Tuple[int, Dict[str, Any]]]] = {}
    for index, spec in indexed:
        face = spec.get("face", {}) if isinstance(spec.get("face"), Mapping) else {}
        key = (_canonical_face_type(face.get("faceType")), str(face.get("looksLevelBand") or looks_level_band(face.get("looksLevel"))))
        groups.setdefault(key, []).append((index, spec))
    rng = random.Random(seed)
    for rows in groups.values():
        rows.sort(key=lambda pair: str(pair[1].get("profileId")))
        rng.shuffle(rows)
    keys = sorted(groups, key=lambda key: (len(groups[key]), key[0], key[1]), reverse=True)
    selected: set[int] = set()
    cursor = 0
    while len(selected) < count and any(groups.values()):
        key = keys[cursor % len(keys)]
        if groups[key]:
            selected.add(groups[key].pop()[0])
        cursor += 1
        if cursor > len(keys) * 10_000:
            break
    return selected


def assign_eyewear_groups_for_batch(
    specs: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Any],
    seed: int,
) -> List[Dict[str, Any]]:
    out = [normalize_spec_defaults(spec) for spec in specs]
    for gender in GENDERS:
        indexed = [(index, spec) for index, spec in enumerate(out) if spec.get("gender") == gender]
        indexed.sort(key=lambda pair: _profile_sort_key(pair[1]))
        counts = _eyewear_target_counts(targets, gender, len(indexed))
        selected = _balanced_eyewear_indices(indexed, counts["with_eyewear"], int(seed) + (2_000 if gender == "female" else 12_000))
        for index, spec in indexed:
            eyewear_group = "glasses" if index in selected else "none"
            rng = random.Random(int(seed) + int(spec.get("identitySeed", 0)) + (31 if eyewear_group == "glasses" else 17))
            out[index]["accessories"] = sample_accessory_spec(gender, rng, eyewear_group=eyewear_group)
            _sync_metadata(out[index])
    return out


def assign_environment_for_batch(
    specs: Sequence[Mapping[str, Any]],
    targets: Optional[Mapping[str, int]] = None,
    seed: int = 20260504,
) -> List[Dict[str, Any]]:
    out = [normalize_spec_defaults(spec) for spec in specs]
    order = ("spring", "summer", "autumn", "winter")
    counts = _scale_counts_largest_remainder(targets or SEASON_TARGETS, count=len(out), order=order)
    indexed = sorted(list(enumerate(out)), key=lambda pair: _profile_sort_key(pair[1]))
    sequence = _spread_values_by_counts(counts, order, seed=int(seed) + 3_000)
    for offset, ((index, spec), season) in enumerate(zip(indexed, sequence)):
        gender = spec["gender"]  # type: ignore[assignment]
        rng = random.Random(int(seed) + int(spec.get("identitySeed", 0)) + offset * 53)
        out[index]["environment"] = _environment_for_season(season, rng)
        out[index]["location"] = _sample_location_for_season(gender, rng, season=season, shot_type="vibe_card")
        out[index]["fashion"] = sample_fashion_spec(gender, rng, season=season)
        out[index]["shotOutfits"] = {
            "faceCard": fashion_upper_outfit(out[index]["fashion"]),
            "fullBody": fashion_full_outfit(out[index]["fashion"]),
        }
        out[index]["vibeActivity"] = sample_vibe_activity_for_location(
            str(out[index]["location"]["locationType"]),
            gender,
            rng,
        )
        out[index]["vibeLocation"] = out[index]["location"]["scene"]
        out[index]["specialCase"] = sample_special_case_spec(gender, rng, season=season)
        _sync_metadata(out[index])
    return out


def _distribution_counts(specs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    face_counts: Counter[str] = Counter()
    looks_counts: Counter[str] = Counter()
    eyewear_counts: Counter[str] = Counter()
    gender_eyewear_counts: Counter[str] = Counter()
    season_counts: Counter[str] = Counter()
    skin_counts: Counter[str] = Counter()
    location_counts: Counter[str] = Counter()
    fashion_counts: Counter[str] = Counter()
    special_counts: Counter[str] = Counter()
    for spec in specs:
        normalized = normalize_spec_defaults(spec)
        face = normalized["face"]
        skin = normalized["skin"]
        accessories = normalized["accessories"]
        environment = normalized["environment"]
        location = normalized["location"]
        fashion = normalized["fashion"]
        special = normalized["specialCase"]
        gender = str(normalized["gender"])
        eyewear_key = "with_eyewear" if accessories["eyewearGroup"] == "glasses" else "without_eyewear"
        face_counts[_canonical_face_type(face.get("faceType"))] += 1
        looks_counts[str(face.get("looksLevelBand") or looks_level_band(face.get("looksLevel")))] += 1
        eyewear_counts[eyewear_key] += 1
        gender_eyewear_counts[f"{gender}_{eyewear_key}"] += 1
        season_counts[str(environment.get("season"))] += 1
        skin_counts[str(skin.get("tone"))] += 1
        location_counts[str(location.get("locationType"))] += 1
        fashion_counts[str(fashion.get("category"))] += 1
        special_counts[str(special.get("type"))] += 1
    for key in FACE_TYPE_ORDER:
        face_counts.setdefault(key, 0)
    for key in LOOKS_LEVEL_BANDS:
        looks_counts.setdefault(key, 0)
    for key in ("with_eyewear", "without_eyewear"):
        eyewear_counts.setdefault(key, 0)
    for gender in GENDERS:
        for key in ("with_eyewear", "without_eyewear"):
            gender_eyewear_counts.setdefault(f"{gender}_{key}", 0)
    gender_eyewear_counts["total_with_eyewear"] = eyewear_counts["with_eyewear"]
    gender_eyewear_counts["total_without_eyewear"] = eyewear_counts["without_eyewear"]
    for key in SEASON_TARGETS:
        season_counts.setdefault(key, 0)
    return {
        "faceType": dict(face_counts),
        "looksLevelBand": dict(looks_counts),
        "eyewear": dict(eyewear_counts),
        "genderEyewear": dict(gender_eyewear_counts),
        "season": dict(season_counts),
        "skinTone": dict(skin_counts),
        "locationType": dict(location_counts),
        "fashionCategory": dict(fashion_counts),
        "specialCase": dict(special_counts),
    }


def audit_prompt_distribution(specs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    counts = _distribution_counts(specs)
    total = len(specs)
    expected: Dict[str, Any] = {}
    mismatches: List[str] = []
    if total == 240:
        expected = {
            "faceType": FACE_TYPE_TARGETS["global"],
            "looksLevelBand": LOOKS_LEVEL_BAND_TARGETS["global"],
            "eyewear": {"with_eyewear": 36, "without_eyewear": 204},
            "genderEyewear": {
                "female_with_eyewear": 12,
                "female_without_eyewear": 108,
                "male_with_eyewear": 24,
                "male_without_eyewear": 96,
                "total_with_eyewear": 36,
                "total_without_eyewear": 204,
            },
            "season": SEASON_TARGETS,
        }
        for section, target in expected.items():
            observed = counts.get(section, {})
            for key, value in target.items():
                if int(observed.get(key, 0)) != int(value):
                    mismatches.append(f"{section}.{key}: expected {value}, got {observed.get(key, 0)}")
    return {
        "promptBuilderVersion": PROMPT_BUILDER_VERSION,
        "promptTargetingVersion": PROMPT_TARGETING_VERSION,
        "metadataVersion": METADATA_VERSION,
        "countingUnit": "identity",
        "identityCount": total,
        "counts": counts,
        "expected": expected,
        "mismatches": mismatches,
        "passed": not mismatches,
    }


def audit_asset_distribution(asset_records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    asset_counts: Counter[str] = Counter()
    shot_expected_counts: Counter[str] = Counter()
    profile_to_eyewear: Dict[str, str] = {}
    temporary_variation_count = 0
    for asset in asset_records:
        group = str(asset.get("eyewearGroup") or "none")
        key = "with_eyewear" if group == "glasses" else "without_eyewear"
        asset_counts[key] += 1
        profile_to_eyewear[str(asset.get("profileId"))] = key
        expected = str(asset.get("shotEyewearExpected") or asset.get("eyewear") or "none")
        shot_expected_counts["with_eyewear" if expected != "none" else "without_eyewear"] += 1
        if bool(asset.get("temporaryEyewearApplied")):
            temporary_variation_count += 1
    identity_counts = Counter(profile_to_eyewear.values())
    return {
        "countingUnit": {"assets": "image", "identities": "identity"},
        "assetCount": len(asset_records),
        "identityCount": len(profile_to_eyewear),
        "eyewearAssetCounts": dict(asset_counts),
        "eyewearIdentityCounts": dict(identity_counts),
        "shotEyewearExpectedCounts": dict(shot_expected_counts),
        "temporaryEyewearVariationCount": temporary_variation_count,
    }


def generate_specs(
    *,
    female_count: int = 0,
    male_count: int = 0,
    start_female: int = 1,
    start_male: int = 1,
    seed: int = 20260504,
    id_width: int = 3,
    exact_distribution: bool = True,
) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    # Stable but distinct seeds by profile.
    for i in range(int(female_count)):
        numeric_id = int(start_female) + i
        specs.append(sample_spec("female", numeric_id, seed=seed + numeric_id, id_width=id_width))
    for i in range(int(male_count)):
        numeric_id = int(start_male) + i
        specs.append(sample_spec("male", numeric_id, seed=seed + 100_000 + numeric_id, id_width=id_width))
    if exact_distribution:
        specs = assign_face_type_groups_for_batch(specs, FACE_TYPE_TARGETS, seed)
        specs = assign_looks_level_bands_for_batch(specs, LOOKS_LEVEL_BAND_TARGETS, seed + 101)
        specs = assign_eyewear_groups_for_batch(specs, EYEWEAR_TARGETS, seed + 202)
        specs = assign_environment_for_batch(specs, SEASON_TARGETS, seed + 303)
        for spec in specs:
            validate_spec(spec)
        audit = audit_prompt_distribution(specs)
        if len(specs) == 240 and not audit["passed"]:
            raise ValueError(f"Exact distribution audit failed: {audit['mismatches']}")
    return specs


# -----------------------------------------------------------------------------
# Validation / export
# -----------------------------------------------------------------------------


def split_positive_and_negative_prompt(prompt: str) -> Tuple[str, str]:
    text = str(prompt or "")
    match = re.search(r"(?im)^Avoid:\s*", text)
    if not match:
        match = re.search(r"(?im)^Negative prompt:\s*", text)
    if not match:
        return text, ""
    return text[: match.start()].strip(), text[match.start() :].strip()


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if re.match(r"^[A-Za-z0-9 _-]+$", term):
        escaped = escaped.replace(r"\ ", r"\s+").replace(r"\-", r"[-_ ]?")
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def _is_negated_context(text: str, start: int) -> bool:
    prefix = text[max(0, start - 96) : start].lower()
    clause = re.split(r"[.;\n]", prefix)[-1]
    negation_markers = (
        "avoid",
        "no ",
        "not ",
        "never",
        "without",
        "free of",
        "blocked",
        "forbidden",
        "does not mean",
        "do not use",
        "do not imply",
    )
    if any(marker in clause for marker in negation_markers):
        return True
    return bool(
        re.search(
            r"(avoid|no|not|never|without|free of|blocked|forbidden|does not mean|do not use|do not imply)\s+([\w /-]+\s+){0,6}$",
            prefix,
        )
    )


def scan_prompt_for_banned_terms(prompt: str, *, include_negative: bool = False) -> List[str]:
    positive, negative = split_positive_and_negative_prompt(prompt)
    scan_text = f"{positive}\n{negative}" if include_negative else positive
    hits: List[str] = []
    for term in BANNED_POSITIVE_TERMS:
        pattern = _term_pattern(term)
        for match in pattern.finditer(scan_text):
            if not include_negative and _is_negated_context(scan_text, match.start()):
                continue
            hits.append(term)
            break
    return sorted(set(hits), key=str.lower)


def validate_no_banned_positive_terms(prompt: str) -> None:
    hits = scan_prompt_for_banned_terms(prompt, include_negative=False)
    if hits:
        raise ValueError(f"Prompt positive block contains banned terms: {', '.join(hits)}")


def validate_catalog_safety() -> None:
    global _CATALOG_SAFETY_VALIDATED
    if _CATALOG_SAFETY_VALIDATED:
        return
    rows: List[Tuple[str, str]] = []
    required_location_fields = {"scene", "allowedShots", "privacyRisk", "logoTextRisk", "seasonCompatibility", "notes"}
    for key, value in LOCATION_CATALOG.items():
        missing = required_location_fields - set(value.keys())
        if missing:
            raise ValueError(f"LOCATION_CATALOG.{key} missing fields: {sorted(missing)}")
        if value.get("privacyRisk") == "high" or value.get("logoTextRisk") == "high":
            raise ValueError(f"LOCATION_CATALOG.{key} has high privacy/logo risk")
        if not set(value.get("allowedShots", [])) <= set(SHOT_TYPES):
            raise ValueError(f"LOCATION_CATALOG.{key} has unsupported allowedShots")
        rows.append((f"LOCATION_CATALOG.{key}.scene", str(value.get("scene", ""))))
        rows.append((f"LOCATION_CATALOG.{key}.notes", str(value.get("notes", ""))))
        if "vibe_card" in value.get("allowedShots", []):
            activities = LOCATION_VIBE_ACTIVITIES.get(key, [])
            if len(activities) < 3:
                raise ValueError(f"LOCATION_VIBE_ACTIVITIES.{key} must define at least three activities")
            for index, activity in enumerate(activities):
                rows.append((f"LOCATION_VIBE_ACTIVITIES.{key}[{index}]", str(activity)))
    required_fashion_fields = {
        "outerwear",
        "tops",
        "bottoms",
        "shoes",
        "bags",
        "palettes",
        "material",
        "fit",
        "bottomVisible",
        "silhouetteReadable",
        "modest",
    }
    for gender, categories in SAFE_FASHION_CATALOG.items():
        for category, value in categories.items():
            missing = required_fashion_fields - set(value.keys())
            if missing:
                raise ValueError(f"SAFE_FASHION_CATALOG.{gender}.{category} missing fields: {sorted(missing)}")
            if value.get("modest") is not True or value.get("silhouetteReadable") is not True:
                raise ValueError(f"SAFE_FASHION_CATALOG.{gender}.{category} must be modest and silhouette-readable")
            for field in ("outerwear", "tops", "bottoms", "shoes", "bags", "palettes", "material", "fit"):
                rows.append((f"SAFE_FASHION_CATALOG.{gender}.{category}.{field}", json.dumps(value.get(field, ""), ensure_ascii=False)))
    for key, value in SPECIAL_CASE_CATALOG.items():
        rows.append((f"SPECIAL_CASE_CATALOG.{key}.notes", str(value.get("notes", ""))))
    problems = [(name, scan_prompt_for_banned_terms(text)) for name, text in rows]
    problems = [(name, hits) for name, hits in problems if hits]
    if problems:
        details = "; ".join(f"{name}: {hits}" for name, hits in problems)
        raise ValueError(f"Unsafe catalog positive terms detected: {details}")
    _CATALOG_SAFETY_VALIDATED = True


def normalize_spec_defaults(spec: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = deepcopy(dict(spec))
    gender = out.get("gender")
    if gender not in GENDERS:
        gender = "female"
        out["gender"] = gender
    profile_id = str(out.get("profileId") or make_profile_id(gender, 1))  # type: ignore[arg-type]
    identity_seed = int(out.get("identitySeed", 10_000 if gender == "female" else 20_000))
    rng = random.Random(identity_seed)
    out.setdefault("schemaVersion", SCHEMA_VERSION)
    out.setdefault("promptBuilderVersion", PROMPT_BUILDER_VERSION)
    out["promptTargetingVersion"] = str(out.get("promptTargetingVersion") or PROMPT_TARGETING_VERSION)
    out.setdefault("metadataVersion", METADATA_VERSION)
    out.setdefault("profileId", profile_id)
    out.setdefault("visualAge", 22)
    out.setdefault("identitySeed", identity_seed)
    out.setdefault("isSynthetic", True)

    if not isinstance(out.get("face"), Mapping):
        out["face"] = sample_face_spec(gender, rng)  # type: ignore[arg-type]
    face = dict(out["face"])
    face["faceType"] = _canonical_face_type(face.get("faceType"))
    face.setdefault("looksLevel", 3.0)
    face["looksLevelBand"] = str(face.get("looksLevelBand") or looks_level_band(face.get("looksLevel")))
    face.setdefault("faceShape", _face_shape_for(face["faceType"], rng))
    face.setdefault("eyeSize", _eye_size_for(face["faceType"], rng))
    face.setdefault("eyeTilt", _eye_tilt_for(face["faceType"], rng))
    face.setdefault("jawline", "soft_defined")
    face.setdefault("cheekFullness", "moderate")
    face.setdefault("noseBridge", "soft_medium")
    face.setdefault("lipFullness", "natural_medium")
    face.setdefault("browThickness", "natural")
    face.setdefault("skinFinish", "natural")
    face.setdefault("vibe", "calm")
    out["face"] = face

    out.setdefault("body", sample_body_spec(gender, rng))  # type: ignore[arg-type]
    out.setdefault("hair", sample_hair_spec(gender, rng))  # type: ignore[arg-type]
    out.setdefault("styling", sample_styling_spec(gender, rng))  # type: ignore[arg-type]
    out.setdefault("skin", {"tone": "natural_beige", "texture": face.get("skinFinish", "natural"), "retouching": "minimal"})
    out.setdefault("accessories", sample_accessory_spec(gender, rng, eyewear_group="none"))  # type: ignore[arg-type]
    out.setdefault("environment", sample_environment_spec(gender, rng))  # type: ignore[arg-type]
    season = str(out["environment"].get("season", "spring")) if isinstance(out.get("environment"), Mapping) else "spring"
    out.setdefault("location", _sample_location_for_season(gender, rng, season=season, shot_type="vibe_card"))  # type: ignore[arg-type]
    out.setdefault("fashion", sample_fashion_spec(gender, rng, season=season))  # type: ignore[arg-type]
    out.setdefault("photo", sample_photo_spec(gender, rng))  # type: ignore[arg-type]
    out.setdefault("specialCase", {"type": "none", "allowed": True, "bottomVisibleOverride": None, "notes": None})

    skin = dict(out["skin"])
    skin.setdefault("tone", "natural_beige")
    skin.setdefault("texture", face.get("skinFinish", "natural"))
    skin.setdefault("retouching", "minimal")
    out["skin"] = skin

    accessories = dict(out["accessories"])
    accessories.setdefault("eyewearGroup", "none")
    accessories.setdefault("eyewear", "none" if accessories.get("eyewearGroup") == "none" else "thin_round_metal")
    accessories.setdefault("hasEyewear", accessories.get("eyewearGroup") == "glasses")
    if accessories.get("eyewearGroup") == "none":
        accessories["canonicalEyewear"] = "none"
    elif accessories.get("canonicalEyewear") in (None, "", "none"):
        accessories["canonicalEyewear"] = accessories.get("eyewear")
    else:
        accessories.setdefault("canonicalEyewear", accessories.get("eyewear"))
    accessories.setdefault("eyewearConsistencyPolicy", "same_across_all_shots")
    accessories.setdefault("temporaryEyewearForShot", {})
    accessories.setdefault("temporaryEyewearAllowed", False)
    accessories.setdefault("temporaryEyewearApplied", False)
    accessories.setdefault("hat", "none")
    accessories.setdefault("bag", "canvas_tote")
    accessories.setdefault("jewelry", "none")
    out["accessories"] = accessories

    environment = dict(out["environment"])
    environment.setdefault("season", "spring")
    environment.setdefault("weather", "clear")
    environment.setdefault("timeOfDay", "daylight")
    environment.setdefault("temperatureFeel", _temperature_for_season(str(environment["season"]), str(environment["weather"])))
    out["environment"] = environment

    location = dict(out["location"])
    raw_location_type = str(location.get("locationType") or "campus_walkway")
    entry_type = raw_location_type if raw_location_type in LOCATION_CATALOG else "campus_walkway"
    entry = LOCATION_CATALOG[entry_type]
    location["locationType"] = raw_location_type
    location.setdefault("scene", entry["scene"])
    location.setdefault("privacyRisk", entry["privacyRisk"])
    location.setdefault("logoTextRisk", entry["logoTextRisk"])
    location.setdefault("allowedShots", list(entry["allowedShots"]))
    out["location"] = location

    fashion = dict(out["fashion"])
    if "category" not in fashion:
        replacement = sample_fashion_spec(gender, rng, season=str(environment["season"]))  # type: ignore[arg-type]
        replacement.update({key: fashion[key] for key in fashion.keys() & {"bottomVisible", "silhouetteReadable", "modest"}})
        fashion = replacement
    fashion.setdefault("modest", True)
    fashion.setdefault("bottomVisible", True)
    fashion.setdefault("silhouetteReadable", True)
    out["fashion"] = fashion

    photo = dict(out["photo"])
    photo.setdefault("realismProfile", "ordinary_smartphone")
    photo.setdefault("cameraMode", "auto")
    photo.setdefault("imperfectionLevel", "mild")
    photo.setdefault("pose", "relaxed natural pose")
    photo.setdefault("gaze", "looking near the camera")
    photo.setdefault("crop", "profile photo crop")
    out["photo"] = photo

    special = dict(out["specialCase"])
    special.setdefault("type", "none")
    entry = SPECIAL_CASE_CATALOG.get(str(special["type"]), SPECIAL_CASE_CATALOG["none"])
    special.setdefault("allowed", bool(entry["allowed"]))
    special.setdefault("bottomVisibleOverride", entry["bottomVisibleOverride"])
    special.setdefault("notes", entry["notes"])
    out["specialCase"] = special

    out.setdefault("shotOutfits", {})
    if isinstance(out["shotOutfits"], Mapping):
        shot_outfits = dict(out["shotOutfits"])
    else:
        shot_outfits = {}
    shot_outfits.setdefault("faceCard", fashion_upper_outfit(fashion))
    shot_outfits.setdefault("fullBody", fashion_full_outfit(fashion))
    out["shotOutfits"] = shot_outfits
    out["vibeActivity"] = normalize_vibe_activity_for_location(
        out.get("vibeActivity"),
        str(location["locationType"]),
        gender,  # type: ignore[arg-type]
        rng,
    )
    out["vibeLocation"] = location["scene"]
    out.setdefault("storagePaths", storage_paths(str(out["profileId"])))
    out.setdefault(
        "shotPlan",
        [{"shotType": shot_type, "storagePath": storage_paths(str(out["profileId"]), shot_type)["storagePath"]} for shot_type in SHOT_TYPES],
    )
    out.setdefault(
        "qa",
        {
            "adultVisual": None,
            "campusRealism": None,
            "noSchoolUniform": None,
            "noRevealingClothes": None,
            "noInfluencerPhotoshoot": None,
            "identityConsistentAcrossShots": None,
            "approved": None,
        },
    )
    _sync_metadata(out)
    return out


def validate_special_case(spec: Mapping[str, Any]) -> None:
    special = spec.get("specialCase", {}) if isinstance(spec.get("specialCase"), Mapping) else {}
    case_type = str(special.get("type") or "none")
    if case_type not in SPECIAL_CASE_CATALOG:
        raise ValueError(f"Disallowed special case: {case_type}")
    if not bool(special.get("allowed", True)):
        raise ValueError(f"Special case is not allowed: {case_type}")
    if special.get("bottomVisibleOverride") not in (True, False, None):
        raise ValueError("specialCase.bottomVisibleOverride must be true, false, or null")


def validate_spec(spec: Mapping[str, Any], *, strict: bool = False) -> None:
    normalized = dict(spec) if strict else normalize_spec_defaults(spec)
    required_top = [
        "schemaVersion",
        "profileId",
        "gender",
        "visualAge",
        "identitySeed",
        "face",
        "body",
        "hair",
        "styling",
        "skin",
        "accessories",
        "environment",
        "location",
        "fashion",
        "photo",
        "specialCase",
    ]
    for key in required_top:
        if key not in normalized:
            raise ValueError(f"spec missing required key: {key}")
    if normalized["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError(f"schemaVersion must be {SCHEMA_VERSION}")
    if normalized["gender"] not in GENDERS:
        raise ValueError(f"gender must be one of {GENDERS}")
    if not is_ai_profile_id(str(normalized["profileId"])):
        raise ValueError("profileId must look like female_137 or male_084")
    if int(normalized["visualAge"]) < 20:
        raise ValueError("visualAge must be 20+ for adult university-student profile assets")

    face = normalized["face"]
    body = normalized["body"]
    hair = normalized["hair"]
    styling = normalized["styling"]
    skin = normalized["skin"]
    accessories = normalized["accessories"]
    environment = normalized["environment"]
    location = normalized["location"]
    fashion = normalized["fashion"]
    photo = normalized["photo"]
    if not isinstance(face, Mapping) or not isinstance(body, Mapping) or not isinstance(hair, Mapping) or not isinstance(styling, Mapping):
        raise ValueError("face/body/hair/styling must be objects")
    if not all(isinstance(section, Mapping) for section in (skin, accessories, environment, location, fashion, photo)):
        raise ValueError("skin/accessories/environment/location/fashion/photo must be objects")
    for key in ["faceType", "looksLevel", "faceShape", "eyeSize", "eyeTilt", "jawline"]:
        if key not in face:
            raise ValueError(f"face missing required key: {key}")
    face_type = _canonical_face_type(face.get("faceType"))
    if face_type not in FACE_TYPE_ORDER:
        raise ValueError("face.faceType is not supported")
    for key in ["heightCm", "bodyFatVisual", "frame", "muscularity", "shoulderWidth", "legRatio"]:
        if key not in body:
            raise ValueError(f"body missing required key: {key}")
    if float(face["looksLevel"]) > 4.4:
        raise ValueError("looksLevel above 4.4 is intentionally blocked for MVP distribution")
    if str(face.get("looksLevelBand") or looks_level_band(face["looksLevel"])) == "4.4-5.0":
        raise ValueError("looksLevelBand 4.4-5.0 is intentionally blocked for MVP distribution")
    if int(body["heightCm"]) < 145 or int(body["heightCm"]) > 200:
        raise ValueError("heightCm out of realistic operating range")
    for key in ["length", "texture", "color", "bangs"]:
        if key not in hair:
            raise ValueError(f"hair missing required key: {key}")
    for key in ["makeupLevel", "fashionMood", "outfitFit"]:
        if key not in styling:
            raise ValueError(f"styling missing required key: {key}")
    if skin.get("tone") not in SKIN_TONE_VISUAL:
        raise ValueError("skin.tone is not supported")
    if skin.get("texture") not in SKIN_VISUAL:
        raise ValueError("skin.texture is not supported")
    if skin.get("retouching") != "minimal":
        raise ValueError("skin.retouching must be minimal")
    if accessories.get("eyewearGroup") not in {"none", "glasses"}:
        raise ValueError("accessories.eyewearGroup must be none or glasses")
    if accessories.get("eyewearGroup") == "none" and accessories.get("eyewear") != "none":
        raise ValueError("eyewear must be none when eyewearGroup is none")
    if accessories.get("eyewearGroup") == "glasses" and accessories.get("eyewear") == "none":
        raise ValueError("eyewear must be a glasses style when eyewearGroup is glasses")
    if accessories.get("eyewear") not in EYEWEAR_VISUAL:
        raise ValueError("eyewear is not supported")
    if accessories.get("canonicalEyewear") not in EYEWEAR_VISUAL:
        raise ValueError("canonicalEyewear is not supported")
    if accessories.get("eyewearGroup") == "none" and accessories.get("canonicalEyewear") != "none":
        raise ValueError("canonicalEyewear must be none when eyewearGroup is none")
    if accessories.get("eyewearGroup") == "glasses" and accessories.get("canonicalEyewear") != accessories.get("eyewear"):
        raise ValueError("canonicalEyewear must match eyewear for eyewear identities")
    if bool(accessories.get("hasEyewear")) != (accessories.get("eyewearGroup") == "glasses"):
        raise ValueError("accessories.hasEyewear must match eyewearGroup")
    if str(accessories.get("eyewearConsistencyPolicy") or "") != "same_across_all_shots":
        raise ValueError("accessories.eyewearConsistencyPolicy must be same_across_all_shots")
    if not isinstance(accessories.get("temporaryEyewearForShot"), Mapping):
        raise ValueError("accessories.temporaryEyewearForShot must be an object")
    if RARE_EYEWEAR_VARIATION_RATE <= 0 and any(bool(accessories.get("temporaryEyewearForShot", {}).get(shot)) for shot in SHOT_TYPES):
        raise ValueError("temporary eyewear variation is disabled")
    if accessories.get("hat") not in {"none", "simple_cap", "beanie"}:
        raise ValueError("accessories.hat is not supported")
    if accessories.get("bag") not in {"canvas_tote", "backpack", "shoulder_bag", "none"}:
        raise ValueError("accessories.bag is not supported")
    if accessories.get("jewelry") not in {"none", "minimal_silver", "simple_watch"}:
        raise ValueError("accessories.jewelry is not supported")
    accessory_text = json.dumps(accessories, ensure_ascii=False)
    if "mask" in accessory_text.lower() or "balaclava" in accessory_text.lower():
        raise ValueError("face-covering accessories are forbidden")
    if environment.get("season") not in SEASON_VISUAL:
        raise ValueError("environment.season is not supported")
    if environment.get("weather") not in WEATHER_VISUAL:
        raise ValueError("environment.weather is not supported")
    if environment.get("timeOfDay") not in TIME_OF_DAY_VISUAL:
        raise ValueError("environment.timeOfDay is not supported")
    if environment.get("temperatureFeel") not in TEMPERATURE_VISUAL:
        raise ValueError("environment.temperatureFeel is not supported")
    if location.get("privacyRisk") == "high" or location.get("logoTextRisk") == "high":
        raise ValueError("location privacy/logo risk must not be high")
    if location.get("locationType") not in LOCATION_CATALOG:
        raise ValueError("location.locationType is not supported")
    for key in ["scene", "privacyRisk", "logoTextRisk", "allowedShots"]:
        if key not in location:
            raise ValueError(f"location missing required key: {key}")
    if not set(location.get("allowedShots", [])) <= set(SHOT_TYPES):
        raise ValueError("location.allowedShots contains unsupported shot types")
    if "vibe_card" in LOCATION_CATALOG[str(location.get("locationType"))].get("allowedShots", []):
        if not vibe_activity_matches_location(str(location.get("locationType")), normalized.get("vibeActivity")):
            raise ValueError("vibeActivity must match location.locationType")
    if fashion.get("category") not in SAFE_FASHION_CATALOG[normalized["gender"]]:
        raise ValueError("fashion.category is not supported")
    for key in ["palette", "outerwear", "top", "bottom", "shoes", "bag", "fit", "material", "bottomVisible", "silhouetteReadable", "modest"]:
        if key not in fashion:
            raise ValueError(f"fashion missing required key: {key}")
    if not isinstance(fashion.get("bottomVisible"), bool):
        raise ValueError("fashion.bottomVisible must be boolean")
    if fashion.get("modest") is not True:
        raise ValueError("fashion.modest must be true")
    if fashion.get("silhouetteReadable") is not True:
        raise ValueError("fashion.silhouetteReadable must be true")
    if photo.get("realismProfile") not in PHOTO_REALISM_VISUAL:
        raise ValueError("photo.realismProfile is not supported")
    if photo.get("cameraMode") != "auto":
        raise ValueError("photo.cameraMode must be auto")
    if photo.get("imperfectionLevel") != "mild":
        raise ValueError("photo.imperfectionLevel must be mild")
    for key in ["pose", "gaze", "crop"]:
        if key not in photo:
            raise ValueError(f"photo missing required key: {key}")
    validate_special_case(normalized)
    metadata_hits = scan_prompt_for_banned_terms(
        json.dumps({"accessories": accessories, "location": location, "fashion": fashion, "specialCase": normalized["specialCase"]}, ensure_ascii=False)
    )
    if metadata_hits:
        raise ValueError(f"Spec metadata contains banned positive terms: {', '.join(metadata_hits)}")
    validate_catalog_safety()
    for shot_type in SHOT_TYPES:
        validate_no_banned_positive_terms(build_prompt(normalized, shot_type, _skip_validation=True))


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")


def write_asset_csv(path: Path, asset_records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "profileId",
        "assetId",
        "gender",
        "shotType",
        "legacyStoragePath",
        "storagePath",
        "promptTargetingVersion",
        "promptHash",
        "prompt",
        "faceType",
        "looksLevelBand",
        "skinTone",
        "eyewear",
        "eyewearGroup",
        "hasEyewear",
        "canonicalEyewear",
        "eyewearConsistencyPolicy",
        "shotEyewearExpected",
        "temporaryEyewearAllowed",
        "temporaryEyewearApplied",
        "season",
        "locationType",
        "fashionCategory",
        "specialCase",
        "bottomVisible",
        "silhouetteReadable",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in asset_records:
            writer.writerow({col: row.get(col, "") for col in columns})


def export_batch(specs: Sequence[Mapping[str, Any]], out_dir: Path) -> Dict[str, str]:
    normalized_specs = [normalize_spec_defaults(spec) for spec in specs]
    asset_records: List[Dict[str, Any]] = []
    for spec in normalized_specs:
        asset_records.extend(build_asset_records(spec))

    specs_jsonl = out_dir / "ai_profile_specs_v3.jsonl"
    assets_jsonl = out_dir / "ai_profile_assets_v3.jsonl"
    assets_csv = out_dir / "ai_profile_assets_v3.csv"
    report_json = out_dir / "ai_profile_distribution_report_v4.json"
    report = {
        "promptDistribution": audit_prompt_distribution(normalized_specs),
        "assetDistribution": audit_asset_distribution(asset_records),
    }
    write_jsonl(specs_jsonl, normalized_specs)
    write_jsonl(assets_jsonl, asset_records)
    write_asset_csv(assets_csv, asset_records)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "specsJsonl": str(specs_jsonl),
        "assetsJsonl": str(assets_jsonl),
        "assetsCsv": str(assets_csv),
        "distributionReportJson": str(report_json),
        "identityCount": str(len(normalized_specs)),
        "assetCount": str(len(asset_records)),
    }


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Spec JSON must be an object")
    return data


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def cmd_sample(args: argparse.Namespace) -> int:
    spec = sample_spec(args.gender, args.numeric_id, seed=args.seed, id_width=args.id_width)
    if args.as_assets:
        rows = build_asset_records(spec)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(spec, ensure_ascii=False, indent=2))
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    spec = load_json(Path(args.spec))
    validate_spec(spec)
    print(build_prompt(spec, args.shot_type))
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    specs = generate_specs(
        female_count=args.female_count,
        male_count=args.male_count,
        start_female=args.start_female,
        start_male=args.start_male,
        seed=args.seed,
        id_width=args.id_width,
        exact_distribution=args.exact_distribution,
    )
    result = export_batch(specs, Path(args.out_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_rec_event_context(args: argparse.Namespace) -> int:
    spec = load_json(Path(args.spec))
    asset = build_asset_record(spec, args.shot_type)
    event = {
        "userId": "<user_id>",
        "type": "like | nope",
        "targetId": spec["profileId"],
        "targetType": "ai_profile",
        "createdAt": "<UTC ISO string>",
        "context": make_rec_event_context(asset),
    }
    print(json.dumps(event, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Seolleyeon AI profile prompt builder v3")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample", help="Print one sampled identity spec or asset records")
    s.add_argument("--gender", required=True, choices=list(GENDERS))
    s.add_argument("--numeric_id", required=True, type=int)
    s.add_argument("--seed", default=None, type=int)
    s.add_argument("--id_width", default=3, type=int)
    s.add_argument("--as_assets", action="store_true")
    s.set_defaults(func=cmd_sample)

    b = sub.add_parser("batch", help="Generate JSONL/CSV prompt batch")
    b.add_argument("--female_count", default=120, type=int)
    b.add_argument("--male_count", default=120, type=int)
    b.add_argument("--start_female", default=1, type=int)
    b.add_argument("--start_male", default=1, type=int)
    b.add_argument("--seed", default=20260504, type=int)
    b.add_argument("--id_width", default=3, type=int)
    b.add_argument("--out_dir", required=True, type=str)
    b.add_argument("--exact_distribution", dest="exact_distribution", action="store_true", default=True)
    b.add_argument("--no_exact_distribution", dest="exact_distribution", action="store_false")
    b.set_defaults(func=cmd_batch)

    pr = sub.add_parser("prompt", help="Build a prompt from one spec JSON file")
    pr.add_argument("--spec", required=True, type=str)
    pr.add_argument("--shot_type", required=True, choices=list(SHOT_TYPES))
    pr.set_defaults(func=cmd_prompt)

    e = sub.add_parser("rec_event_context", help="Print recEvent context example for one spec and shot")
    e.add_argument("--spec", required=True, type=str)
    e.add_argument("--shot_type", required=True, choices=list(SHOT_TYPES))
    e.set_defaults(func=cmd_rec_event_context)

    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
