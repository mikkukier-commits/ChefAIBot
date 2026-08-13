from agno.tools.tavily import TavilyTools
from agno.tools import tool
from agno.models.google import Gemini
from agno.agent import Agent

import pandas as pd
import streamlit as st
import os
import certifi
import time


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
# SESSION STATE
# =========================================================

if "request_count" not in st.session_state:
    st.session_state.request_count = 0

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

# Debugger data
if "debug_data" not in st.session_state:
    st.session_state.debug_data = {
        "last_response_time": None,
        "total_response_time": 0.0,
        "last_input_tokens": None,
        "last_output_tokens": None,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "last_prompt_length": 0,
        "last_response_length": 0,
        "last_error": None,
        "last_request": None,
        "database_status": "Не перевірено",
        "recipe_count": 0,
    }

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

    except Exception:
        return pd.DataFrame()


# =========================================================
# LOAD DATABASE
# =========================================================

recipes_df = load_recipes()

if recipes_df.empty:
    st.session_state.debug_data["database_status"] = (
        "Помилка / порожня база"
    )
    st.session_state.debug_data["recipe_count"] = 0
else:
    st.session_state.debug_data["database_status"] = (
        "Підключено"
    )
    st.session_state.debug_data["recipe_count"] = len(recipes_df)


# =========================================================
# SIDEBAR DEBUGGER
# =========================================================

with st.sidebar:

    st.header("Debugger")

    st.caption(
        "Дані доступні тільки для поточної Streamlit-сесії."
    )

    st.divider()

    # -----------------------------------------------------
    # SESSION
    # -----------------------------------------------------

    st.subheader("Session")

    st.metric(
        "AI-запити",
        f"{st.session_state.request_count}/{MAX_REQUESTS_PER_SESSION}"
    )

    st.metric(
        "Повідомлень у контексті",
        len(st.session_state.messages)
    )

    # -----------------------------------------------------
    # DATABASE
    # -----------------------------------------------------

    st.subheader("Google Sheets")

    st.write(
        f"**Статус:** "
        f"{st.session_state.debug_data['database_status']}"
    )

    st.write(
        f"**Рецептів:** "
        f"{st.session_state.debug_data['recipe_count']}"
    )

    # -----------------------------------------------------
    # TOKEN USAGE
    # -----------------------------------------------------

    st.subheader("Token usage")

    input_tokens = st.session_state.debug_data[
        "last_input_tokens"
    ]

    output_tokens = st.session_state.debug_data[
        "last_output_tokens"
    ]

    total_input_tokens = st.session_state.debug_data[
        "total_input_tokens"
    ]

    total_output_tokens = st.session_state.debug_data[
        "total_output_tokens"
    ]

    if input_tokens is None:
        st.write("**Останній input:** N/A")
    else:
        st.write(
            f"**Останній input:** {input_tokens:,}"
        )

    if output_tokens is None:
        st.write("**Останній output:** N/A")
    else:
        st.write(
            f"**Останній output:** {output_tokens:,}"
        )

    st.write(
        f"**Всього input:** {total_input_tokens:,}"
    )

    st.write(
        f"**Всього output:** {total_output_tokens:,}"
    )

    total_tokens = (
        total_input_tokens
        + total_output_tokens
    )

    st.metric(
        "Всього токенів",
        f"{total_tokens:,}"
    )

    # -----------------------------------------------------
    # PERFORMANCE
    # -----------------------------------------------------

    st.subheader("Performance")

    response_time = st.session_state.debug_data[
        "last_response_time"
    ]

    if response_time is not None:
        st.write(
            f"**Остання відповідь:** "
            f"{response_time:.2f} сек."
        )
    else:
        st.write(
            "**Остання відповідь:** N/A"
        )

    total_time = st.session_state.debug_data[
        "total_response_time"
    ]

    st.write(
        f"**Сумарний час:** {total_time:.2f} сек."
    )

    # -----------------------------------------------------
    # PROMPT
    # -----------------------------------------------------

    st.subheader("Last request")

    last_request = st.session_state.debug_data[
        "last_request"
    ]

    if last_request:
        st.write(
            f"**Довжина запиту:** "
            f"{len(last_request)} символів"
        )

        with st.expander("Показати запит"):
            st.write(last_request)

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    st.subheader("Last response")

    response_length = st.session_state.debug_data[
        "last_response_length"
    ]

    st.write(
        f"**Довжина відповіді:** "
        f"{response_length} символів"
    )

    # -----------------------------------------------------
    # ERROR
    # -----------------------------------------------------

    last_error = st.session_state.debug_data[
        "last_error"
    ]

    if last_error:

        st.subheader("Last error")

        st.error(last_error)

    # -----------------------------------------------------
    # RESET
    # -----------------------------------------------------

    st.divider()

    if st.button(
        "Очистити debugger",
        use_container_width=True
    ):

        st.session_state.debug_data = {
            "last_response_time": None,
            "total_response_time": 0.0,
            "last_input_tokens": None,
            "last_output_tokens": None,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "last_prompt_length": 0,
            "last_response_length": 0,
            "last_error": None,
            "last_request": None,
            "database_status": (
                "Підключено"
                if not recipes_df.empty
                else "Помилка / порожня база"
            ),
            "recipe_count": len(recipes_df),
        }

        st.rerun()


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
            results.append(
                format_recipe(row)
            )

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
        ingredients = normalize_text(
            row["ingredients"]
        )
        description = normalize_text(
            row["description"]
        )

        search_text = (
            f"{name} "
            f"{ingredients} "
            f"{description}"
        )

        if q in search_text:
            results.append(
                format_recipe(row)
            )

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
    """

    if (
        original_portions <= 0
        or desired_portions <= 0
    ):
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

    Google Sheets є ЄДИНИМ джерелом рецептів
    у базі даних.

    НЕ ВИГАДУЙ рецепти.

    Якщо рецепту немає в Google Sheets,
    не створюй власний рецепт замість нього.
    """,

    """
    ПРАВИЛА ПОШУКУ:

    Якщо користувач просить конкретний рецепт,
    обов'язково використовуй recipe_search.

    Якщо користувач просить рецепт за дієтичними
    критеріями, також обов'язково використовуй
    recipe_search.

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

    ОБОВ'ЯЗКОВО використовуй історію
    поточної розмови.

    Якщо користувач спочатку сказав:

    "Мені потрібна страва без лактози
    та без глютену."

    а потім:

    "Будь-яку страву."

    це означає:

    "Знайди будь-яку страву без лактози
    та без глютену."

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

    "На жаль, у моїй базі даних немає рецепту,
    який відповідає цим критеріям.
    Бажаєте, щоб я пошукав його в інтернеті?"

    НЕ використовуй Tavily без явного підтвердження.
    """,

    """
    Якщо користувач явно погоджується
    на пошук в інтернеті:

    "так"
    "давай"
    "шукай"
    "пошукай"

    можна використовувати TavilyTools.

    Але використовуй його тільки після
    явного підтвердження.
    """,

    """
    Якщо користувач задає питання,
    яке не стосується:

    - кулінарії;
    - рецептів;
    - їжі;
    - інгредієнтів;
    - приготування їжі;

    відповідай:

    "Я кулінарний чат-помічник ratAItool
    і спеціалізуюся на питаннях, пов'язаних
    із кулінарією, рецептами та харчуванням.
    На жаль, я не можу допомогти з цим питанням."
    """,

    """
    Якщо користувач повідомляє своє ім'я,
    можеш використовувати його в подальшій
    розмові.

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
            id="gemini-3.1-flash-lite"
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
# TOKEN / USAGE EXTRACTION
# =========================================================

def extract_usage(response):
    """
    Tries to extract token usage from an Agno response.

    Returns:
        input_tokens, output_tokens
    """

    input_tokens = None
    output_tokens = None

    try:

        metrics = getattr(
            response,
            "metrics",
            None
        )

        if metrics:

            if isinstance(metrics, dict):

                input_tokens = (
                    metrics.get("input_tokens")
                    or metrics.get("prompt_tokens")
                )

                output_tokens = (
                    metrics.get("output_tokens")
                    or metrics.get("completion_tokens")
                )

            else:

                input_tokens = getattr(
                    metrics,
                    "input_tokens",
                    None
                )

                if input_tokens is None:
                    input_tokens = getattr(
                        metrics,
                        "prompt_tokens",
                        None
                    )

                output_tokens = getattr(
                    metrics,
                    "output_tokens",
                    None
                )

                if output_tokens is None:
                    output_tokens = getattr(
                        metrics,
                        "completion_tokens",
                        None
                    )

    except Exception:
        pass

    # Try response-level attributes
    if input_tokens is None:
        try:
            input_tokens = getattr(
                response,
                "input_tokens",
                None
            )
        except Exception:
            pass

    if output_tokens is None:
        try:
            output_tokens = getattr(
                response,
                "output_tokens",
                None
            )
        except Exception:
            pass

    # Convert to int where possible
    try:
        if input_tokens is not None:
            input_tokens = int(input_tokens)
    except Exception:
        input_tokens = None

    try:
        if output_tokens is not None:
            output_tokens = int(output_tokens)
    except Exception:
        output_tokens = None

    return input_tokens, output_tokens


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
    # SAVE DEBUG REQUEST
    # =====================================================

    st.session_state.debug_data[
        "last_request"
    ] = prompt

    st.session_state.debug_data[
        "last_prompt_length"
    ] = len(prompt)

    st.session_state.debug_data[
        "last_error"
    ] = None

    # =====================================================
    # BUILD CONTEXT
    # =====================================================

    conversation_context = (
        build_conversation_context()
    )

    # =====================================================
    # BUILD AGENT PROMPT
    # =====================================================

    agent_prompt = f"""
Нижче наведена історія поточної розмови.

ОБОВ'ЯЗКОВО використовуй її для
розуміння контексту.

Особливо звертай увагу на:

- попередні рецепти;
- дієтичні обмеження;
- алергії;
- уподобання;
- займенники;
- фрази "будь-яку", "так", "давай";
- фрази "цей рецепт", "ця страва",
  "вона", "він".

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
який вже був знайдений у попередніх
повідомленнях, використовуй саме цей контекст.

Не вимагай від користувача повторно
називати рецепт, якщо він очевидний
з історії розмови.
"""

    # =====================================================
    # AGENT RESPONSE
    # =====================================================

    with st.chat_message("assistant"):

        with st.spinner("🧠 Думаю..."):

            start_time = time.perf_counter()

            try:

                response = (
                    st.session_state
                    .chef_agent
                    .run(agent_prompt)
                )

                elapsed_time = (
                    time.perf_counter()
                    - start_time
                )

                response_text = response.content

                # -------------------------------------------------
                # Extract token usage
                # -------------------------------------------------

                (
                    input_tokens,
                    output_tokens
                ) = extract_usage(response)

                st.session_state.debug_data[
                    "last_input_tokens"
                ] = input_tokens

                st.session_state.debug_data[
                    "last_output_tokens"
                ] = output_tokens

                if input_tokens is not None:
                    st.session_state.debug_data[
                        "total_input_tokens"
                    ] += input_tokens

                if output_tokens is not None:
                    st.session_state.debug_data[
                        "total_output_tokens"
                    ] += output_tokens

                # -------------------------------------------------
                # Performance
                # -------------------------------------------------

                st.session_state.debug_data[
                    "last_response_time"
                ] = elapsed_time

                st.session_state.debug_data[
                    "total_response_time"
                ] += elapsed_time

                st.session_state.debug_data[
                    "last_response_length"
                ] = len(response_text)

            except Exception as e:

                elapsed_time = (
                    time.perf_counter()
                    - start_time
                )

                error_text = str(e)

                st.session_state.debug_data[
                    "last_error"
                ] = error_text

                st.session_state.debug_data[
                    "last_response_time"
                ] = elapsed_time

                st.session_state.debug_data[
                    "total_response_time"
                ] += elapsed_time

                response_text = (
                    "Виникла помилка під час роботи "
                    f"чат-помічника: {error_text}"
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

    # =====================================================
    # REFRESH SIDEBAR DEBUGGER
    # =====================================================

    st.rerun()


# =========================================================
# USAGE INFORMATION
# =========================================================

st.divider()

st.caption(
    f"Використано запитів: "
    f"{st.session_state.request_count}/"
    f"{MAX_REQUESTS_PER_SESSION}"
)
