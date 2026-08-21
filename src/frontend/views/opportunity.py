import streamlit as st

from components import (
    render_empty_state,
    render_list_section,
    render_sidebar_logo,
    render_signal_group,
)

import front_config as config


def find_opportunity_by_id(
    opportunity_spaces: list[dict],
    selected_opportunity_id: str | None,
) -> dict | None:
    if not selected_opportunity_id:
        return None

    return next(
        (
            space
            for space in opportunity_spaces
            if space.get("id") == selected_opportunity_id
        ),
        None,
    )


def render_opportunity_detail(
    opportunity_spaces: list[dict],
    selected_opportunity_id: str | None = None,
) -> None:
    selected_from_radar = find_opportunity_by_id(
        opportunity_spaces,
        selected_opportunity_id,
    )
    default_domain = (
        selected_from_radar.get("domain")
        if selected_from_radar
        else config.ORANGE_BUSINESS_DOMAINS[0]
    )
    domain_index = (
        config.ORANGE_BUSINESS_DOMAINS.index(default_domain)
        if default_domain in config.ORANGE_BUSINESS_DOMAINS
        else 0
    )

    selected_domain = st.sidebar.selectbox(
        "Domain",
        config.ORANGE_BUSINESS_DOMAINS,
        index=domain_index,
    )

    domain_opportunity_spaces = [
        space
        for space in opportunity_spaces
        if space.get("domain", "Unassigned") == selected_domain
    ]

    if not domain_opportunity_spaces:
        st.sidebar.markdown("**Opportunity spaces**")
        st.sidebar.caption("No opportunity spaces for this domain yet.")
        render_sidebar_logo()
        st.caption(f"Domain: {selected_domain}")
        st.header("No opportunity spaces found")
        render_empty_state(
            "Empty domain."
        )
        st.stop()

    opportunity_names = [
        space.get("technology_name", "Untitled opportunity")
        for space in domain_opportunity_spaces
    ]
    default_opportunity_name = (
        selected_from_radar.get("technology_name")
        if selected_from_radar
        and selected_from_radar.get("domain") == selected_domain
        else opportunity_names[0]
    )
    opportunity_index = (
        opportunity_names.index(default_opportunity_name)
        if default_opportunity_name in opportunity_names
        else 0
    )

    selected_name = st.sidebar.selectbox(
        "Opportunity space",
        opportunity_names,
        index=opportunity_index,
    )

    render_sidebar_logo()

    selected_space = next(
        space
        for space in domain_opportunity_spaces
        if space.get("technology_name", "Untitled opportunity") == selected_name
    )

    st.caption(f"Domain: {selected_space.get('domain', 'Unassigned')}")
    st.header(selected_space.get("technology_name", "Untitled opportunity"))
    st.write(selected_space.get("overview_definition", "No overview available."))

    scoring = selected_space.get("scoring", {})
    score_col_1, score_col_2 = st.columns(2)

    with score_col_1:
        st.metric(
            "Attractiveness",
            f"{scoring.get('attractiveness_score', 'N/A')}/10",
        )
        st.write(scoring.get("attractiveness_rationale", "No text available."))

    with score_col_2:
        st.metric(
            "Urgency",
            f"{scoring.get('urgency_score', 'N/A')}/10",
        )
        st.write(scoring.get("urgency_rationale", "No text available."))

    signals_tab, use_cases_tab, audience_tab, raw_data_tab = st.tabs(
        ["Signals", "Use cases", "Target audience", "Raw data"]
    )

    with signals_tab:
        signals = selected_space.get("signals_and_sources", {})
        render_signal_group("Regulation", signals.get("regulation", []))
        render_signal_group("Buying signals", signals.get("buying_signals", []))
        render_signal_group("Market trends", signals.get("market_trends", []))

    with use_cases_tab:
        use_cases = selected_space.get("use_cases_and_value_drivers", [])

        if not use_cases:
            render_empty_state("No use cases listed.")
        else:
            for use_case in use_cases:
                st.subheader(use_case.get("use_case", "Untitled use case"))
                st.write(use_case.get("value_driver", "No value driver provided."))

    with audience_tab:
        audience = selected_space.get("target_audience", {})
        audience_col_1, audience_col_2, audience_col_3 = st.columns(3)

        with audience_col_1:
            render_list_section("Personas", audience.get("personas", []))

        with audience_col_2:
            render_list_section("Verticals", audience.get("verticals", []))

        with audience_col_3:
            render_list_section("Geographies", audience.get("geographies", []))

    with raw_data_tab:
        st.json(selected_space)
