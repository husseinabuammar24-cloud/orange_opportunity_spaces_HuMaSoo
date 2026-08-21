import streamlit as st

from components import render_sidebar_logo
import front_config as config


DOMAIN_COLORS = {
    "Smart Industries": "#6c6c6c",
    "Connectivity Solutions": "#1f77b4",
    "Cybersecurity": "#ff7900",
    "Cloud": "#8f8f8f",
    "Customer Experience": "#00a3a3",
    "Employee Experience": "#7a4db3",
    "Sustainability": "#4b8f29",
}


def get_score(space: dict, score_name: str, default: int = 0) -> int:
    score = space.get("scoring", {}).get(score_name, default)
    if isinstance(score, (int, float)):
        return max(0, min(10, int(score)))
    return default


def urgency_to_radius(urgency_score: int) -> int:
    return max(1, min(10, 11 - urgency_score))


def get_domain_angles() -> dict[str, float]:
    slice_width = 360 / len(config.ORANGE_BUSINESS_DOMAINS)
    return {
        domain: index * slice_width
        for index, domain in enumerate(config.ORANGE_BUSINESS_DOMAINS)
    }


def build_radar_rows(opportunity_spaces: list[dict]) -> list[dict]:
    rows = []

    for space in opportunity_spaces:
        domain = space.get("domain", "Unassigned")
        attractiveness = get_score(space, "attractiveness_score")
        urgency = get_score(space, "urgency_score")

        rows.append(
            {
                "ID": space.get("id", ""),
                "Domain": domain,
                "Opportunity space": space.get("technology_name", "Untitled opportunity"),
                "Attractiveness": attractiveness,
                "Urgency": urgency,
            }
        )

    return rows


def get_clicked_point_id(clicked_points: list[dict], point_ids: list[str]) -> str | None:
    if not clicked_points:
        return None

    point = clicked_points[0]
    customdata = point.get("customdata")
    if customdata:
        return customdata[0] if isinstance(customdata, list) else customdata

    point_index = point.get("pointIndex", point.get("pointNumber"))
    if isinstance(point_index, int) and 0 <= point_index < len(point_ids):
        return point_ids[point_index]

    return None


def render_radar(opportunity_spaces: list[dict]) -> None:
    try:
        import plotly.graph_objects as go
    except ModuleNotFoundError:
        st.error("Plotly is required for the radar view. Install it with: pip install plotly")
        return

    try:
        from streamlit_plotly_events2 import plotly_events
    except ModuleNotFoundError:
        st.error(
            "Clickable radar dots require streamlit-plotly-events2. "
            "Install it with: pip install streamlit-plotly-events2"
        )
        return

    render_sidebar_logo()
    st.header("Opportunity Radar")
    st.caption("Slice = domain | Ring = urgency | Dot size = attractiveness")

    domain_angles = get_domain_angles()
    slice_width = 360 / len(config.ORANGE_BUSINESS_DOMAINS)

    theta = []
    radius = []
    sizes = []
    colors = []
    labels = []
    point_ids = []
    hover_text = []

    for space in opportunity_spaces:
        domain = space.get("domain")
        if domain not in domain_angles:
            continue

        urgency = get_score(space, "urgency_score")
        attractiveness = get_score(space, "attractiveness_score")

        theta.append(domain_angles[domain])
        radius.append(urgency_to_radius(urgency))
        sizes.append(14 + attractiveness * 4)
        colors.append(DOMAIN_COLORS.get(domain, "#ff7900"))
        labels.append(space.get("id", ""))
        point_ids.append(space.get("id", ""))
        hover_text.append(
            f"<b>{space.get('technology_name', 'Untitled opportunity')}</b><br>"
            f"ID: {space.get('id', 'N/A')}<br>"
            f"Domain: {domain}<br>"
            f"Attractiveness: {attractiveness}/10<br>"
            f"Urgency: {urgency}/10"
        )

    fig = go.Figure()

    for index, domain in enumerate(config.ORANGE_BUSINESS_DOMAINS):
        fig.add_trace(
            go.Barpolar(
                r=[10],
                theta=[domain_angles[domain]],
                width=[slice_width],
                marker=dict(
                    color="#f4f4f4",
                    line=dict(color="#dedede", width=1),
                    opacity=0.55,
                ),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    fig.add_trace(
        go.Scatterpolar(
            r=radius,
            theta=theta,
            mode="markers+text",
            text=labels,
            textposition="top center",
            customdata=point_ids,
            marker=dict(
                size=sizes,
                color=colors,
                line=dict(color="#000000", width=1),
                opacity=0.9,
            ),
            hovertext=hover_text,
            hoverinfo="text",
            showlegend=False,
        )
    )

    fig.update_layout(
        height=650,
        showlegend=False,
        polar=dict(
            radialaxis=dict(
                range=[0, 10],
                tickvals=[2, 5, 8],
                ticktext=["Now", "Next", "Later"],
                gridcolor="#cfcfcf",
                showline=False,
            ),
            angularaxis=dict(
                tickmode="array",
                tickvals=list(domain_angles.values()),
                ticktext=config.ORANGE_BUSINESS_DOMAINS,
                direction="clockwise",
                rotation=90,
                gridcolor="#dedede",
            ),
            bgcolor="#ffffff",
        ),
        margin=dict(l=40, r=40, t=40, b=40),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )

    clicked_points = plotly_events(
        fig,
        click_event=True,
        hover_event=False,
        select_event=False,
        override_height=650,
        key="opportunity_radar",
        config={"displayModeBar": False},
    )

    selected_point_id = get_clicked_point_id(clicked_points, point_ids)
    if selected_point_id:
        st.session_state["selected_opportunity_id"] = selected_point_id
        st.session_state["pending_view"] = "Opportunity detail"
        st.rerun()

    st.subheader("Opportunity spaces")
    st.dataframe(
        build_radar_rows(opportunity_spaces),
        use_container_width=True,
        hide_index=True,
    )
