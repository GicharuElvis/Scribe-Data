"""
Module for processing Unicode based corpuses for autosuggestion and autocompletion generation.

.. raw:: html
    <!--
    * Copyright (C) 2024 Scribe
    *
    * This program is free software: you can redistribute it and/or modify
    * it under the terms of the GNU General Public License as published by
    * the Free Software Foundation, either version 3 of the License, or
    * (at your option) any later version.
    *
    * This program is distributed in the hope that it will be useful,
    * but WITHOUT ANY WARRANTY; without even the implied warranty of
    * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    * GNU General Public License for more details.
    *
    * You should have received a copy of the GNU General Public License
    * along with this program.  If not, see <https://www.gnu.org/licenses/>.
    -->
"""

import csv
import json
from pathlib import Path

import emoji
from icu import Char, UProperty
from tqdm.auto import tqdm

from scribe_data.unicode.unicode_utils import (
    get_emoji_codes_to_ignore,
)
from scribe_data.utils import (
    DEFAULT_JSON_EXPORT_DIR,
    get_language_iso,
)

emoji_codes_to_ignore = get_emoji_codes_to_ignore()


def gen_emoji_lexicon(
    language: str,
    emojis_per_keyword: int,
):
    """
    Generates a dictionary of keywords (keys) and emoji unicode(s) associated with them (values).

    Parameters
    ----------
        language : string (default=None)
            The language keywords are being generated for.

        emojis_per_keyword : int (default=None)
            The limit for number of emoji keywords that should be generated per keyword.

    Returns
    -------
        Keywords dictionary for emoji keywords-to-unicode are saved locally or uploaded to Scribe apps.
    """

    keyword_dict = {}

    iso = get_language_iso(language)
    # Pre-set up the emoji popularity data.
    popularity_dict = {}

    with (Path(__file__).parent / "2021_ranked.tsv").open() as popularity_file:
        tsv_reader = csv.DictReader(popularity_file, delimiter="\t")
        for tsv_row in tsv_reader:
            popularity_dict[tsv_row["Emoji"]] = int(tsv_row["Rank"])

    # Pre-set up handling flags and tags (subdivision flags).
    # emoji_flags = Char.getBinaryPropertySet(UProperty.RGI_EMOJI_FLAG_SEQUENCE)
    # emoji_tags = Char.getBinaryPropertySet(UProperty.RGI_EMOJI_TAG_SEQUENCE)
    # regexp_flag_keyword = re.compile(r".*\: (?P<flag_keyword>.*)")

    annotations_file_path = (
        Path(__file__).parent
        / "cldr-annotations-full"
        / "annotations"
        / f"{iso}"
        / "annotations.json"
    )
    annotations_derived_file_path = (
        Path(__file__).parent
        / "cldr-annotations-derived-full"
        / "annotationsDerived"
        / f"{iso}"
        / "annotations.json"
    )

    cldr_file_paths = {
        "annotations": annotations_file_path,
        "annotationsDerived": annotations_derived_file_path,
    }

    for cldr_file_key, cldr_file_path in cldr_file_paths.items():
        with open(cldr_file_path, "r") as file:
            cldr_data = json.load(file)

        cldr_dict = cldr_data[cldr_file_key]["annotations"]

        for cldr_char in tqdm(
            iterable=cldr_dict,
            desc=f"Characters processed from '{cldr_file_key}' CLDR file for {language}",
            unit="cldr characters",
        ):
            # Filter CLDR data for emoji characters while not including certain emojis.
            if (
                cldr_char in emoji.EMOJI_DATA
                and cldr_char.encode("utf-8") not in emoji_codes_to_ignore
            ):
                emoji_rank = popularity_dict.get(cldr_char)

                # Process for emoji variants.
                has_modifier_base = Char.hasBinaryProperty(
                    cldr_char, UProperty.EMOJI_MODIFIER_BASE
                )
                if has_modifier_base and len(cldr_char) > 1:
                    continue

                # Only fully-qualified emoji should be generated by keyboards.
                # See www.unicode.org/reports/tr51/#Emoji_Implementation_Notes.
                if (
                    emoji.EMOJI_DATA[cldr_char]["status"]
                    == emoji.STATUS["fully_qualified"]
                ):
                    emoji_annotations = cldr_dict[cldr_char]

                    # # Process for flag keywords.
                    # if cldr_char in emoji_flags or cldr_char in emoji_tags:
                    #     flag_keyword_match = regexp_flag_keyword.match(
                    #         emoji_annotations["tts"][0]
                    #     )
                    #     flag_keyword = flag_keyword_match.group("flag_keyword")
                    #     keyword_dict.setdefault(flag_keyword, []).append(
                    #         {
                    #             "emoji": cldr_char,
                    #             "is_base": has_modifier_base,
                    #             "rank": emoji_rank,
                    #         }
                    #     )

                    for emoji_keyword in emoji_annotations["default"]:
                        emoji_keyword = emoji_keyword.lower()  # lower case the key
                        if (
                            # Use single-word annotations as keywords.
                            len(emoji_keyword.split()) == 1
                        ):
                            keyword_dict.setdefault(emoji_keyword, []).append(
                                {
                                    "emoji": cldr_char,
                                    "is_base": has_modifier_base,
                                    "rank": emoji_rank,
                                }
                            )

    # Check nouns files for plurals and update their data with the emojis for their singular forms.
    language_nouns_path = Path(DEFAULT_JSON_EXPORT_DIR) / f"{language}" / "nouns.json"
    if not language_nouns_path.is_file():
        print(
            "\nNote: Getting a language's nouns before emoji keywords allows for plurals to be linked to the emojis for their singulars.\n"
        )

    else:
        print(
            "\nNouns file detected in the same export directory. Linking singular word emojis to their plurals.\n"
        )
        with open(
            language_nouns_path,
            encoding="utf-8",
        ) as f:
            noun_data = json.load(f)

        plurals_to_singulars_dict = {
            noun_data[row]["plural"].lower(): row.lower()
            for row in noun_data
            if noun_data[row]["plural"] != "isPlural"
        }

        for plural, singular in plurals_to_singulars_dict.items():
            if plural not in keyword_dict and singular in keyword_dict:
                keyword_dict[plural] = keyword_dict[singular]

    # Sort by rank after all emojis already found per keyword.
    for emojis in keyword_dict.values():
        emojis.sort(
            key=lambda suggestion: float("inf")
            if suggestion["rank"] is None
            else suggestion["rank"]
        )

        # If specified, enforce limit of emojis per keyword.
        if emojis_per_keyword and len(emojis) > emojis_per_keyword:
            emojis[:] = emojis[:emojis_per_keyword]

    return keyword_dict
