# Frontend Documentation

This folder contains the Streamlit frontend for the Orange Business Innovation Radar. The frontend files were separated in a `frontend/` folder so the UI can evolve independently.

Run the frontend from the project root with:

```powershell
streamlit run src/frontend/app.py
```

## Files Overview

- `assets/`: Graphical assets such as OB logo and CSS.
- `app.py`: Streamlit entrypoint. Loads global assets and data, renders the hero, and routes between the Radar and Opportunity detail views.
- `front_config.py`: Shared configuration file for frontend. !! Separate from main config.py
- `data_loader.py`: Data and asset loading helpers (db loading, CSS, logo base64 conversion).
- `components.py`: Reusable UI components such as the hero, empty-state messages, signal sections, audience lists, and sidebar logo.
- `views/opportunity.py`: Opportunity Space detail page. Lets the user select a domain and opportunity space, then displays scores, signals, use cases, audience, and raw data.
- `views/radar.py`: Radar dashboard page. Builds the sonar-style Plotly radar and handles clicks on opportunity dots.

## `app.py`

This is the main Streamlit file. Its job is to initialize the app and decide which view to show.

Main responsibilities:

- Configure the Streamlit page title and layout.
- Load CSS from the configured stylesheet path.
- Render the shared hero/header.
- Load opportunity spaces from SQLite(?) database.
- Create the sidebar `View` selector.
- Route to either the Radar view or the Opportunity detail view.
- Manage view navigation from radar clicks through `st.session_state`.

Logic flow:

1. `st.set_page_config(...)` sets browser/page metadata and wide layout.
2. `load_css(config.CSS_PATH)` injects custom CSS into the Streamlit page.
3. `render_hero()` displays the branded page header.
4. `load_opportunity_spaces(config.DB_PATH)` reads the opportunity-space data.
5. If no data is found, Streamlit shows an error and stops.
6. `pending_view` is checked before the sidebar widget is created. This is important because Streamlit does not allow modifying an already-created widget key during the same run. It is required to make radar dots clickable :')
7. The `View` selectbox chooses between `Radar` and `Opportunity detail`.
8. The selected view function is called.


## `front_config.py`

This file stores frontend constants in one place. 

Import it as:
```python
import front_config as config
```

This keeps path and domain configuration consistent across the frontend.

Constants:

- `PROJECT_ROOT`: Resolves the project root from `src/frontend/front_config.py`.
- `DATA_PATH`: Path to data. For now `data/os_example.json`.
- `CSS_PATH`: Path to CSS. For now `assets/alt_styles.css`.
- `LOGO_PATH`: Path to OB Logo. For now `assets/ob_logo.png`.
- `ORANGE_BUSINESS_DOMAINS`: Domain list.


## `data_loader.py`

This file contains helpers for reading local files used by the frontend.

### `load_opportunity_spaces(path: Path) -> list[dict]`

Loads opportunity-space data from a SQLite database.

Working logic:

- Opens a connection to the database.
- Configures the connection to return database rows that can be accessed by column name.
- Queries the opportunity_space table to retrieve the basic opportunity information.
- Orders the opportunities by their database ID.
- Passes each opportunity to `build_opportunity_space()` to assemble its complete data.
- `build_opportunity_space()` retrieves additional information from related tables.
- Returns a list of assembled opportunity-space dictionaries.
- Closes the database connection when finished.
- Uses `@st.cache_data`, so Streamlit caches the result and does not reread the file on every rerun unless the input changes.
- See the .py file for more details about helper functions like `build_opportunity_space()`.

### `load_css(path: Path) -> None`

Injects a CSS file into the Streamlit page.

Working logic:

- Opens the CSS file with UTF-8 encoding.
- Wraps the CSS content in a `<style>` tag.
- Sends it to Streamlit. `unsafe_allow_html=True` allows Streamlit to interpret the HTML/CSS instead of displaying it as plain text.

### `image_to_base64(path: Path) -> str`

Converts an image file into a base64 string so it can be rendered through plain HTML.

Working logic:

- Reads the image bytes from disk.
- Encodes those bytes with Python's built-in `base64` module.
- Decodes the result to UTF-8 text.
- Uses `@st.cache_data` because the logo does not need to be reprocessed on every rerun.


## `components.py`

This file contains reusable UI pieces used by multiple views.

### `get_logo_img_html(class_name: str) -> str`

Returns an HTML `<img>` tag for the Orange Business logo.

Working logic:

- Checks whether `config.LOGO_PATH` exists.
- If the logo is missing, returns an empty string.
- Converts the logo to base64 using `image_to_base64`(from `data_loader.py`).
- Returns an HTML image tag using the provided CSS class name.


### `render_hero() -> None`

Displays the main branded hero/header area.

Working logic:

- Uses `st.markdown` to enable HTML.
- Inserts the logo HTML from `get_logo_img_html("ob-logo-main")`.
- Displays the Innovation Radar title and subtitle.


### `render_empty_state(message: str) -> None`

Displays a message using ob-empty CSS styling.

Working logic:

- Wraps the message in a `<div class="ob-empty">`.
- Used when a section has no signals, no use cases, or no opportunities for a selected domain.


### `render_signal_group(title: str, signals: list[dict]) -> None`

Displays one group of signals.

Working logic:

- Displays the group title with `st.subheader`.
- If the list is empty, displays the empty state.
- For each signal:
  - reads `title`, `insight`, and `url`
  - displays the signal title in bold when available
  - displays the insight text
  - displays an `Open source` link button when a URL exists

Expected signal shape:

```json
{
  "title": "Signal title",
  "insight": "Why this signal matters",
  "url": "https://example.com"
}
```

### `render_list_section(title: str, items: list[str]) -> None`

Displays a simple text list. Used for personas, verticals, and geographies.

Working logic:

- Displays the section title with `st.subheader`.
- If there are no items, displays an empty state.
- Otherwise writes each item as a bullet.


### `render_sidebar_logo() -> None`

Displays the logo at the bottom of the sidebar.

Working logic:

- Adds a horizontal divider with `st.sidebar.markdown("---")`.
- Checks whether the logo file exists.
- Converts the logo to base64.
- Renders it as HTML inside a wrapper `<div class="ob-sidebar-logo-wrap">`.
- Position is controlled with CSS.


## `views/opportunity.py`

This file contains the detailed page for one opportunity space.

### `find_opportunity_by_id(opportunity_spaces: list[dict], selected_opportunity_id: str | None) -> dict | None`

Finds one opportunity space by its `id`.

Working logic:

- If no ID is provided, returns `None`.
- Otherwise loops through the opportunity-space list.
- Returns the first item whose `id` matches `selected_opportunity_id`.
- Returns `None` if no matching opportunity is found.

This is used when a user clicks a dot in the Radar view. The selected ID is stored in session state and passed into the detail view.

### `render_opportunity_detail(opportunity_spaces: list[dict], selected_opportunity_id: str | None = None) -> None`

Renders the full Opportunity detail page.

Working logic:

- Checks whether a selected opportunity ID was passed from the Radar view.
- If yes, finds that opportunity and uses its domain/opportunity as the default sidebar selection. If not, defaults to the first domain.
- Shows a sidebar domain selectbox using `config.ORANGE_BUSINESS_DOMAINS`.
- Filters opportunity spaces to only those matching the selected domain.
- If the selected domain has no opportunities:
  - shows a sidebar empty message
  - renders the sidebar logo
  - shows a page-level empty state
  - stops the page with `st.stop()`
- If opportunities exist:
  - shows an opportunity-space selectbox in the sidebar
  - renders the sidebar logo
  - finds the selected opportunity object
  - displays domain, title, overview, attractiveness score, urgency score, and rationales
  - creates tabs for Signals, Use cases, Target audience, and Raw data

Tabs:

- `Signals`: Uses `render_signal_group` for regulation, buying signals, and market trends.
- `Use cases`: Shows each use case and its value driver.
- `Target audience`: Shows personas, verticals, and geographies in three columns.
- `Raw data`: Shows the selected opportunity-space JSON with `st.json`.


## `views/radar.py`

This file contains the sonar-style radar dashboard.

The intended encoding is:
- Slice = domain
- Ring/radius = urgency
- Dot size = attractiveness
- Dot label/hover = opportunity ID/name


### `get_score(space: dict, score_name: str, default: int = 0) -> int`

Reads a score from an opportunity space.

Working logic:

- Looks inside `space["scoring"]` for the requested score.
- Accepts numeric values only.
- Clamps the score between 0 and 10.
- Returns 0 if the score is missing or not numeric.

Used for both attractiveness_score and urgency_score.


### `urgency_to_radius(urgency_score: int) -> int`

Converts urgency into a radar radius.

Working logic:

- High urgency should appear closer to the center.
- The formula is 11 - urgency_score.
- The result is clamped between 1 and 10 so points stay visible inside the chart.

Examples:
- urgency 10 -> radius 1, close to center
- urgency 5 -> radius 6
- urgency 1 -> radius 10, outer ring


### `get_domain_angles() -> dict[str, float]`

Assigns each Orange Business domain to an angle around the radar.

Working logic:

- Divides 360 degrees by the number of configured domains.
- Uses the index of each domain in `config.ORANGE_BUSINESS_DOMAINS`.
- Returns a mapping like `{"Cybersecurity": 102.85, ...}`.


### `build_radar_rows(opportunity_spaces: list[dict]) -> list[dict]`

Builds the summary table displayed under the radar.

Working logic:

- Loops through all opportunity spaces.
- Extracts ID, domain, technology name, attractiveness score, and urgency score.
- Returns a list of dictionaries that Streamlit displays with `st.dataframe`.


### `get_clicked_point_id(clicked_points: list[dict], point_ids: list[str]) -> str | None`

Extracts the selected opportunity ID from Plotly click-event data.

Working logic:

- If no point was clicked, returns None.
- Reads the first clicked point from the event list.
- First tries to read customdata, which is where the chart stores opportunity IDs.
- If customdata is not available, falls back to the clicked point index.
- Uses the index to look up the matching ID from point_ids.
- Returns None if no ID can be resolved.


### `render_radar(opportunity_spaces: list[dict]) -> None`

Renders the radar dashboard.

Working logic:

- Imports Plotly inside the function. If Plotly is missing, shows an install message.
- Imports plotly_events from streamlit_plotly_events2.
- Renders the sidebar logo.
- Displays the radar title and encoding caption.
- Builds arrays for Plotly:
  - `theta`: domain angle
  - `radius`: urgency converted to distance from center
  - `sizes`: attractiveness converted to marker size
  - `colors`: domain-specific dot color
  - `labels`: opportunity IDs displayed near dots
  - `point_ids`: opportunity IDs used for click navigation
  - `hover_text`: detailed hover tooltip content
- Adds one Barpolar trace per domain to create the slice backgrounds.
- Adds one Scatterpolar trace for opportunity-space dots.
- Configures ring labels, angular labels, colors, and chart size.
- Renders the chart with `plotly_events` so dot clicks can be captured.
- If a dot is clicked:
  - saves the selected opportunity ID in `st.session_state["selected_opportunity_id"]`
  - saves a pending navigation request in `st.session_state["pending_view"]`
  - reruns the app
- Displays the summary table under the radar.

Navigation note:

The Radar view does not directly write to `st.session_state["selected_view"]` because Streamlit does not allow changing a widget key after that widget has been created. Instead, it writes `pending_view`, and `app.py` applies that pending view before creating the sidebar `View` selector on the next run.
