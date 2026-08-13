from agno.tools.tavily import TavilyTools
from agno.tools import tool
from agno.models.google import Gemini
from agno.agent import Agent

import pandas as pd
import streamlit as st
import os
import certifi


# =========================================================
# CONFIGURATION
# =========================================================

MAX_REQUESTS_PER_SESSION = 20
MAX_MESSAGE_LENGTH = 1000
MAX_CONTEXT_MESSAGES = 20


# =========================================================
# SSL CONFIGURATION
# =========================================================

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="ratAItool — Кулінарний AI-помічник",
    page_icon="🍳",
    layout="centered"
)


# =========================================================
# HEADER
# =========================================================

st.title("🍳 ratAItool")
st.caption("Кулінарний чат-помічник")


# =========================================================
# SESSION LIMITS
# =========================================================

if "request_count" not in st.session_state:
    st.session_state.request_count = 0


# =========================================================
# GOOGLE SHEETS DATABASE
# =========================================================

@st.cache_data(ttl="1m")
def load_recipes():
    """
    Loads recipes from Google Sheets.

    Google Sheets is the ONLY recipe database.
    There is no local fallback database.
    """

    try:
        from streamlit_gsheets import GSheetsConnection

        conn = st.connection(
            "gsheets",
            type=GSheetsConnection
        )

        df = conn.read(ttl="1m")

        if df is None or df.empty:
            st.error("Google Sheets не містить рецептів.")
            return pd.DataFrame()

        # Normalize column names
        df.columns = [
            str(column).strip().lower()
            for column in df.columns
        ]

        required_columns = [
            "name",
            "ingredients",
            "description",
            "lactose free",
            "gluten free"
        ]

        missing_columns = [
            column
            for column in required_columns
            if column not in df.columns
        ]

        if missing_columns:
            st.error(
                "У Google Sheets відсутні необхідні колонки: "
                + ", ".join(missing_columns)
            )
            return pd.DataFrame()

        # Replace NaN values
        df = df.fillna("")

        # Normalize dietary flags
        df["lactose free"] = (
            df["lactose free"]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        df["gluten free"] = (
            df["gluten free"]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        return df

    except Exception as e:
        st.error(
            f"Не вдалося завантажити рецепти з Google Sheets: {e}"
        )
        return pd.DataFrame()


recipes_df = load_recipes()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def format_recipe(row):
    """
    Converts one Google Sheets row into readable text.
    """

    lactose_free = str(
        row.get("lactose free", "")
    ).strip().lower()

    gluten_free = str(
        row.get("gluten free", "")
    ).strip().lower()

    return (
        f"🍳 Рецепт: {row['name']}\n"
        f"Інгредієнти: {row['ingredients']}\n"
        f"Приготування: {row['description']}\n"
        f"Без лактози: {lactose_free}\n"
        f"Без глютену: {gluten_free}"
    )


def normalize_text(text):
    """
    Normalizes text for searching.
    """

    return str(text).strip().lower()


# =========================================================
# RECIPE SEARCH TOOL
# =========================================================

@tool
def recipe_search(query: str) -> str:
    """
    Searches the Google Sheets recipe database.

    IMPORTANT:
    This is the ONLY source of recipes.

    The tool can search:
    - recipe names
    - ingredients
    - descriptions
    - lactose-free recipes
    - gluten-free recipes
    - recipes satisfying both restrictions

    Examples:
    - "борщ"
    - "паста"
    - "запечені яблука"
    - "без лактози"
    - "без глютену"
    - "без лактози та без глютену"

    Args:
        query: Recipe name or dietary requirement.

    Returns:
        Matching recipes or NOT_FOUND.
    """

    if recipes_df.empty:
        return "DATABASE_EMPTY"

    if not query or not query.strip():
        return "NOT_FOUND"

    q = normalize_text(query)

    # -----------------------------------------------------
    # Detect dietary requirements
    # -----------------------------------------------------

    lactose_required = (
        "лактоз" in q
        or "lactose" in q
        or "без молока" in q
        or "безлактоз" in q
    )

    gluten_required = (
        "глютен" in q
        or "gluten" in q
        or "безглютен" in q
    )

    # -----------------------------------------------------
    # Dietary search
    # -----------------------------------------------------

    if lactose_required or gluten_required:

        filtered_df = recipes_df.copy()

        if lactose_required:
            filtered_df = filtered_df[
                filtered_df["lactose free"].isin(
                    ["yes", "true", "так", "1"]
                )
            ]

        if gluten_required:
            filtered_df = filtered_df[
                filtered_df["gluten free"].isin(
                    ["yes", "true", "так", "1"]
                )
            ]

        if filtered_df.empty:
            return "NOT_FOUND"

        results = []

        for _, row in filtered_df.iterrows():
            results.append(format_recipe(row))

        return (
            f"Знайдено рецептів: {len(results)}\n\n"
            + "\n\n".join(results)
        )

    # -----------------------------------------------------
    # Normal recipe/name search
    # -----------------------------------------------------

    results = []

    for _, row in recipes_df.iterrows():

        name = normalize_text(row["name"])
        ingredients = normalize_text(row["ingredients"])
        description = normalize_text(row["description"])

        search_text = (
            f"{name} "
            f"{ingredients} "
            f"{description}"
        )

        if q in search_text:
            results.append(format_recipe(row))

    if not results:
        return "NOT_FOUND"

    return (
        f"Знайдено рецептів: {len(results)}\n\n"
        + "\n\n".join(results)
    )


# =========================================================
# PORTION CALCULATOR
# =========================================================

@tool
def calculate_recipe_portions(
    original_portions: int,
    desired_portions: int,
    ingredient_amount: float
) -> str:
    """
    Calculates a new ingredient amount for a different
    number of portions.

    Args:
        original_portions: Original number of portions.
        desired_portions: Desired number of portions.
        ingredient_amount: Original ingredient amount.
    """

    if original_portions <= 0 or desired_portions <= 0:
        return (
            "Помилка: кількість порцій повинна бути "
            "більшою за 0."
        )

    new_amount = (
        ingredient_amount
        * desired_portions
        / original_portions
    )

    return (
        f"Для {desired_portions} порцій потрібно "
        f"{new_amount:g} одиниць інгредієнта "
        f"(було {ingredient_amount:g} "
        f"на {original_portions} порцій)."
    )


# =========================================================
# AGENT INSTRUCTIONS
# =========================================================

instructions = [

    """
    Ти — ratAItool, кулінарний чат-помічник.

    Твоє завдання:

    - знаходити рецепти;
    - знаходити рецепти за дієтичними обмеженнями;
    - аналізувати рецепти;
    - відповідати на питання про інгредієнти;
    - розраховувати кількість інгредієнтів;
    - за необхідності шукати рецепти в інтернеті.

    Відповідай виключно українською мовою.
    """,

    """
    ВАЖЛИВО:

    Google Sheets є ЄДИНИМ джерелом рецептів у базі даних.

    НЕ ВИГАДУЙ рецепти.

    Якщо рецепту немає в Google Sheets,
    не створюй власний рецепт замість нього.
    """,

    """
    ПРАВИЛА ПОШУКУ:

    Якщо користувач просить конкретний рецепт,
    обов'язково використовуй recipe_search.

    Якщо користувач просить рецепт за дієтичними критеріями,
    також обов'язково використовуй recipe_search.

    Наприклад:

    "хочу щось без лактози"
    "потрібна безглютенова страва"
    "знайди щось без лактози та глютену"
    "будь-яка безлактозна страва"

    У таких випадках шукай безпосередньо
    в Google Sheets.
    """,

    """
    КОНТЕКСТ:

    ОБОВ'ЯЗКОВО використовуй історію поточної розмови.

    Якщо користувач спочатку сказав:

    "Мені потрібна страва без лактози та без глютену."

    а потім:

    "Будь-яку страву."

    це означає:

    "Знайди будь-яку страву без лактози та без глютену."

    НЕ ВТРАЧАЙ попередні критерії.
    """,

    """
    Якщо користувач говорить:

    "вона"
    "він"
    "цей рецепт"
    "ця страва"
    "а він?"
    "а вона?"
    "чи підходить вона?"

    і зрозуміло, що йдеться про рецепт,
    який щойно був знайдений або обговорений,

    використовуй цей рецепт із історії розмови.

    Не вимагай повторно називати рецепт.
    """,

    """
    Якщо recipe_search повертає NOT_FOUND:

    НЕ ВИГАДУЙ рецепт.

    Скажи:

    "На жаль, у моїй базі даних немає рецепту, який відповідає цим критеріям. Бажаєте, щоб я пошукав його в інтернеті?"

    НЕ використовуй Tavily без явного підтвердження.
    """,

    """
    Якщо користувач явно погоджується на пошук в інтернеті:

    "так"
    "давай"
    "шукай"
    "пошукай"

    можна використовувати TavilyTools.

    Але використовуй його тільки після явного підтвердження.
    """,

    """
    Якщо користувач задає питання, яке не стосується:

    - кулінарії;
    - рецептів;
    - їжі;
    - інгредієнтів;
    - приготування їжі;

    відповідай:

    "Я кулінарний чат-помічник ratAItool і спеціалізуюся на питаннях, пов'язаних із кулінарією, рецептами та харчуванням. На жаль, я не можу допомогти з цим питанням."
    """,

    """
    Якщо користувач повідомляє своє ім'я,
    можеш використовувати його в подальшій розмові.

    Не вимагай від користувача повідомляти ім'я.
    """
]


# =========================================================
# AGENT INITIALIZATION
# =========================================================

if "chef_agent" not in st.session_state:

    st.session_state.chef_agent = Agent(
        name="ratAItool",

        model=Gemini(
            id="gemini-3.5-flash-lite"
        ),

        tools=[
            recipe_search,
            calculate_recipe_portions,
            TavilyTools()
        ],

        instructions=instructions,

        markdown=True
    )


# =========================================================
# CHAT HISTORY
# =========================================================

if "messages" not in st.session_state:

    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Привіт! Я ratAItool, кулінарний "
                "чат-помічник. Чим я можу сьогодні допомогти?"
            )
        }
    ]


# =========================================================
# DISPLAY CHAT HISTORY
# =========================================================

for message in st.session_state.messages:

    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# =========================================================
# BUILD CONVERSATION CONTEXT
# =========================================================

def build_conversation_context():

    # Use only the latest messages to avoid
    # continuously growing token usage.

    messages = st.session_state.messages[
        -MAX_CONTEXT_MESSAGES:
    ]

    context_parts = []

    for message in messages:

        role = message["role"]

        if role == "user":
            role_name = "Користувач"
        else:
            role_name = "ratAItool"

        context_parts.append(
            f"{role_name}: {message['content']}"
        )

    return "\n\n".join(context_parts)


# =========================================================
# USER INPUT
# =========================================================

prompt = st.chat_input(
    "Напишіть ваше питання..."
)


if prompt:

    # =====================================================
    # MESSAGE LENGTH LIMIT
    # =====================================================

    if len(prompt) > MAX_MESSAGE_LENGTH:

        st.warning(
            f"Повідомлення занадто довге. "
            f"Максимальна довжина — "
            f"{MAX_MESSAGE_LENGTH} символів."
        )

        st.stop()

    # =====================================================
    # REQUEST LIMIT
    # =====================================================

    if (
        st.session_state.request_count
        >= MAX_REQUESTS_PER_SESSION
    ):

        st.error(
            "Ви досягли максимальної кількості "
            f"запитів за цю сесію: "
            f"{MAX_REQUESTS_PER_SESSION}."
        )

        st.info(
            "Ліміт потрібен для контролю використання "
            "AI-моделі та API."
        )

        st.stop()

    # =====================================================
    # SAVE USER MESSAGE
    # =====================================================

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )

    with st.chat_message("user"):
        st.markdown(prompt)

    # =====================================================
    # INCREASE REQUEST COUNTER
    # =====================================================

    st.session_state.request_count += 1

    # =====================================================
    # BUILD CONTEXT
    # =====================================================

    conversation_context = build_conversation_context()

    # =====================================================
    # BUILD AGENT PROMPT
    # =====================================================

    agent_prompt = f"""
Нижче наведена історія поточної розмови.

ОБОВ'ЯЗКОВО використовуй її для розуміння контексту.

Особливо звертай увагу на:

- попередні рецепти;
- дієтичні обмеження;
- алергії;
- уподобання;
- займенники;
- фрази "будь-яку", "так", "давай";
- фрази "цей рецепт", "ця страва", "вона", "він".

================ ІСТОРІЯ РОЗМОВИ ================

{conversation_context}

================ КІНЕЦЬ ІСТОРІЇ ==================

Поточний запит користувача:

{prompt}

===================================================

Відповідай на поточний запит.

Якщо користувач шукає рецепт
або рецепт за дієтичними критеріями —
використовуй recipe_search.

Якщо користувач посилається на рецепт,
який вже був знайдений у попередніх повідомленнях,
використовуй саме цей контекст.

Не вимагай від користувача повторно
називати рецепт, якщо він очевидний
з історії розмови.
"""

    # =====================================================
    # AGENT RESPONSE
    # =====================================================

    with st.chat_message("assistant"):

        with st.spinner("🧠 Думаю..."):

            try:

                response = (
                    st.session_state
                    .chef_agent
                    .run(agent_prompt)
                )

                response_text = response.content

            except Exception as e:

                response_text = (
                    "Виникла помилка під час роботи "
                    f"чат-помічника: {e}"
                )

            st.markdown(response_text)

    # =====================================================
    # SAVE ASSISTANT RESPONSE
    # =====================================================

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": response_text
        }
    )


# =========================================================
# USAGE INFORMATION
# =========================================================

st.divider()

st.caption(
    f"Використано запитів: "
    f"{st.session_state.request_count}/"
    f"{MAX_REQUESTS_PER_SESSION}"
)
