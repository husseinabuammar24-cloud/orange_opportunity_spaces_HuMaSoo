import streamlit as st

from data_loader import image_to_base64
import front_config as config


def get_logo_img_html(class_name: str) -> str:
    if not config.LOGO_PATH.exists():
        return ""

    logo_base64 = image_to_base64(config.LOGO_PATH)
    return f'<img class="{class_name}" src="data:image/png;base64,{logo_base64}" alt="Orange Business logo">'


def render_hero() -> None:
    st.markdown(
        f"""
        <section class="ob-hero">
          {get_logo_img_html("ob-logo-main")}
          <h1 class="ob-hero-title">Innovation Radar</h1>
          <p class="ob-hero-copy">Draft viewer for Orange Business Opportunity Spaces</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(message: str) -> None:
    st.markdown(f'<div class="ob-empty">{message}</div>', unsafe_allow_html=True)


def render_signal_group(title: str, signals: list[dict]) -> None:
    st.subheader(title)

    if not signals:
        render_empty_state(f"No {title.lower()} found.")
        return

    for signal in signals:
        signal_title = signal.get("title")
        insight = signal.get("insight", "No insight provided.")
        url = signal.get("url")

        if signal_title:
            st.markdown(f"**{signal_title}**")
        st.write(insight)
        if url:
            st.link_button("Open source", url)


def render_list_section(title: str, items: list[str]) -> None:
    st.subheader(title)

    if not items:
        render_empty_state(f"No {title.lower()} listed.")
        return

    for item in items:
        st.write(f"- {item}")


def render_sidebar_logo() -> None:
    st.sidebar.markdown("---")
    if not config.LOGO_PATH.exists():
        return

    logo_base64 = image_to_base64(config.LOGO_PATH)
    st.sidebar.markdown(
        (
            '<div class="ob-sidebar-logo-wrap">'
            f'<img class="ob-logo-sidebar" src="data:image/png;base64,{logo_base64}" alt="Orange Business logo">'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
