#!/usr/bin/env python3
"""Self-check for default_bin_cluster_name (bsimvis/app/services/cluster_utils.py).

Binary clusters used to default their name to the most common raw member
filename, which for malware samples is often a long scanner-submission string.
This pins the new precedence: AV family > YARA rule > truncated filename > the
caller's generic fallback.

No redis, no fixtures: pure function over three frequency lists.
Run: python3 scripts/test_default_bin_cluster_name.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bsimvis.app.services.cluster_utils import default_bin_cluster_name  # noqa: E402

FALLBACK = "Binary Cluster 42"


def test_avtype_wins_over_everything():
    name = default_bin_cluster_name(
        names_list=["SecuriteInfo.com.Trojan.Siggen21.63024.25599.exe"],
        avtype_list=["Emotet", "Emotet", "Gafgyt"],
        yara_list=["MALWARE_Win_Trojan_Generic"],
        fallback=FALLBACK,
    )
    assert name == "Emotet", name


def test_yara_wins_when_no_avtype():
    name = default_bin_cluster_name(
        names_list=["some_long_sample_name_1234567890abcdef.bin"],
        avtype_list=[],
        yara_list=["MALWARE_Win_Trojan_Generic", "MALWARE_Win_Trojan_Generic"],
        fallback=FALLBACK,
    )
    assert name == "MALWARE_Win_Trojan_Generic", name


def test_short_filename_used_verbatim():
    name = default_bin_cluster_name(
        names_list=["dropper.exe", "dropper.exe", "payload.exe"],
        avtype_list=[],
        yara_list=[],
        fallback=FALLBACK,
    )
    assert name == "dropper.exe", name


def test_long_filename_gets_truncated():
    long_name = "SecuriteInfo.com.Trojan.Siggen21.63024.25599.exe"
    name = default_bin_cluster_name(
        names_list=[long_name],
        avtype_list=[],
        yara_list=[],
        fallback=FALLBACK,
    )
    assert len(name) <= 40, name
    assert name.endswith("..."), name
    assert long_name.startswith(name[:-3]), name


def test_fallback_when_nothing_known():
    name = default_bin_cluster_name(
        names_list=[], avtype_list=[], yara_list=[], fallback=FALLBACK
    )
    assert name == FALLBACK, name


def test_tag_distribution_family_wins_over_legacy_lists():
    # Plan D, Decision 8: tag_distribution's family axis (mint-on-write av:
    # tags) outranks the legacy avtype_list, same precedence order as before.
    name = default_bin_cluster_name(
        names_list=["dropper.exe"],
        avtype_list=["Gafgyt"],
        yara_list=[],
        fallback=FALLBACK,
        tag_distribution={
            "family": [
                {
                    "tag_id": "av",
                    "count": 5,
                    "children": [
                        {
                            "tag_id": "av:clamav",
                            "count": 5,
                            "children": [
                                {
                                    "tag_id": "av:clamav:mirai",
                                    "count": 5,
                                    "children": [],
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )
    assert name == "mirai", name


def test_tag_distribution_yara_fallback_when_no_family():
    name = default_bin_cluster_name(
        names_list=["dropper.exe"],
        avtype_list=[],
        yara_list=["legacy_rule"],
        fallback=FALLBACK,
        tag_distribution={
            "family": [],
            "yara": [
                {
                    "tag_id": "yara",
                    "count": 3,
                    "children": [
                        {
                            "tag_id": "yara:trojan",
                            "count": 3,
                            "children": [
                                {
                                    "tag_id": "yara:trojan:mirai",
                                    "count": 3,
                                    "children": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    )
    assert name == "mirai", name


def test_tag_distribution_absent_falls_back_to_legacy():
    name = default_bin_cluster_name(
        names_list=["dropper.exe"],
        avtype_list=["Gafgyt"],
        yara_list=[],
        fallback=FALLBACK,
        tag_distribution=None,
    )
    assert name == "Gafgyt", name


if __name__ == "__main__":
    test_avtype_wins_over_everything()
    test_yara_wins_when_no_avtype()
    test_short_filename_used_verbatim()
    test_long_filename_gets_truncated()
    test_fallback_when_nothing_known()
    test_tag_distribution_family_wins_over_legacy_lists()
    test_tag_distribution_yara_fallback_when_no_family()
    test_tag_distribution_absent_falls_back_to_legacy()
    print("OK")
