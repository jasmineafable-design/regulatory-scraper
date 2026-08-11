from core.notify_channels import EmailNotificationChannel


def test_exact_regulator_category_match_wins():
    channel = EmailNotificationChannel(
        recipient_matrix={
            ("IC", "IC-CL"): ["compliance@x.com"],
            ("IC", "IC-ADVISORY"): ["legal@x.com"],
        },
        default_recipients=["fallback@x.com"],
    )
    assert channel._recipients_for("IC", "IC-CL") == ["compliance@x.com"]
    assert channel._recipients_for("IC", "IC-ADVISORY") == ["legal@x.com"]


def test_falls_back_to_regulator_wide_when_category_unmatched():
    channel = EmailNotificationChannel(
        recipient_matrix={("BIR", "RMC"): ["tax@x.com"]},
        default_recipients=["fallback@x.com"],
    )
    # Same regulator, a category with no specific mapping -> regulator-wide recipients.
    assert channel._recipients_for("BIR", "RR") == ["tax@x.com"]


def test_falls_back_to_default_when_regulator_unmatched():
    channel = EmailNotificationChannel(
        recipient_matrix={("BIR", "RMC"): ["tax@x.com"]},
        default_recipients=["fallback@x.com"],
    )
    assert channel._recipients_for("SEC", "SEC-MC") == ["fallback@x.com"]
