import gradio as gr
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from ttb_ride.config import COVER_IMAGE_PATH, CONGRATS_IMAGE_PATH, DEFAULT_BG_R, DEFAULT_BG_G, DEFAULT_BG_B
from ttb_ride.state import TState, new_state
from ttb_ride.ui_theme import hero_css_base, bg_style_tag, layout_style_tag
from ttb_ride.utils.images import path_from_gradio_file
from ttb_ride.utils.debug import get_debug_text
from ttb_ride.agents import (
    set_engine,
    router_intent, general_chat, agent2_docops, agent3_appraisal,
    route_after_router, route_after_docops
)
from ttb_ride.llm.engine import TtbRideEngine
from ttb_ride.utils.images import image_path_to_data_url

from dotenv import load_dotenv
load_dotenv(override=True)


def build_graph():
    g = StateGraph(TState)
    g.add_node("router", router_intent)
    g.add_node("chat", general_chat)
    g.add_node("docops", agent2_docops)
    g.add_node("appraise", agent3_appraisal)
    g.set_entry_point("router")
    g.add_conditional_edges("router", route_after_router, {"docops": "docops", "chat": "chat", "END": END})
    g.add_conditional_edges("docops", route_after_docops, {"appraise": "appraise", "END": END})
    g.add_edge("appraise", END)
    g.add_edge("chat", END)

    return g.compile(checkpointer=MemorySaver())


# ===== Gradio wiring helpers =====
def render_chat(messages):
    convo, user_buf = [], None
    for role, text in messages:
        if role == "user":
            user_buf = text
        elif role == "assistant":
            convo.append([user_buf, text])
            user_buf = None
    return convo


def gr_update_visibility(state: TState):
    show_up = state["ui"]["show_uploads"]
    need = state["ui"]["need"]
    show_sat = state["ui"]["show_satisfaction"]
    return (
        gr.update(visible=show_up),  # bike
        gr.update(visible=show_up),  # income
        gr.update(visible=show_up),  # id
        gr.update(visible=show_sat), # Happy
        gr.update(visible=show_sat), # Unhappy
        f"Docs: "
        f"Bike [{'✅' if not need['bike'] else '⬜'}] | "
        f"Income [{'✅' if not need['income'] else '⬜'}] | "
        f"ID [{'✅' if not need['id'] else '⬜'}]"
    )


def _clear_text():
    return ""


def make_ui(compiled_graph):
    from ttb_ride.agents import feedback_extra_system  # local import to avoid cycle
    from ttb_ride.llm.engine import ENGINE  # already set by set_engine()

    with gr.Blocks(title="TTB Ride — Agentic AI Motorcycle loans Demo",
                   css=hero_css_base()) as demo:

        # background + layout CSS
        gr.HTML(bg_style_tag(DEFAULT_BG_R, DEFAULT_BG_G, DEFAULT_BG_B))
        gr.HTML(layout_style_tag())

        # ----- HERO COVER -----
        with gr.Column(elem_classes=["hero-wrap"]):
            try:
                gr.Image(value=COVER_IMAGE_PATH, show_label=False, interactive=False, elem_classes=["hero-img"])
            except Exception:
                gr.Markdown("> _(Cover image not found; set COVER_IMAGE_PATH env var to a valid image.)_")
            gr.HTML('<div class="hero-title">TTB Ride — Agentic AI Chatbot Motorcycle loans Demo</div>')
            gr.HTML('<div class="hero-sub">service “ เมื่อคุณขอ คุณพร้อมจ่าย เราพร้อมให้ ” operated by AI Chatbot</div>')

        # ===== TOP: CHAT (full width) =====
        with gr.Column(elem_classes=["main-chat"]):
            chat = gr.Chatbot(label="Chat", height=560)
            user_in = gr.Textbox(placeholder="Welcome to TTB Ride service...", label="Message")

        # ===== BOTTOM: LEFT (upload docs) | RIGHT (debug) =====
        with gr.Row(elem_classes=["bottom-row"]):
            with gr.Column(scale=1, min_width=320, elem_classes=["upload-pane", "card"]):
                gr.Markdown("**Upload documents** (auto-appears when loan intent is detected)")
                docs_status = gr.Markdown("Docs: Bike [⬜] | Income [⬜] | ID [⬜]")
                up_bike   = gr.File(label="① รูปมอเตอร์ไซค์", file_types=["image"], type="filepath", visible=False)
                up_income = gr.File(label="② เอกสารรายได้ (สลิปเงินเดือน)", file_types=["image"], type="filepath", visible=False)
                up_id     = gr.File(label="③ บัตรประชาชน", file_types=["image"], type="filepath", visible=False)
                with gr.Row():
                    btn_sat   = gr.Button("Happy", visible=False)
                    btn_unsat = gr.Button("Unhappy", visible=False)

            with gr.Column(scale=2, min_width=420, elem_classes=["card"]):
                gr.Markdown("**Debug log**")
                debug_md = gr.Markdown("_(no debug logs yet)_")

                with gr.Accordion("Orchestration Graph", open=False):
                    graph_img = gr.Image(label="LangGraph graph", interactive=False)
                    btn_graph = gr.Button("Refresh graph")

        # ===== State =====
        st = gr.State(new_state())

        # ===== Handlers =====
        def _invoke(state: TState) -> TState:
            return compiled_graph.invoke(state, config={"configurable": {"thread_id": "ttb-ride-session"}})

        def on_user_submit(user_text, st: TState):
            st["messages"].append(("user", user_text))
            st = _invoke(st)
            return render_chat(st["messages"]), *gr_update_visibility(st), get_debug_text(st), st

        def on_upload_bike(file_payload, st: TState):
            path = path_from_gradio_file(file_payload)
            if path:
                st["docs"]["bike"]["path"] = path
            st = _invoke(st)
            return render_chat(st["messages"]), *gr_update_visibility(st), get_debug_text(st), st

        def on_upload_income(file_payload, st: TState):
            path = path_from_gradio_file(file_payload)
            if path:
                st["docs"]["income"]["path"] = path
            st = _invoke(st)
            return render_chat(st["messages"]), *gr_update_visibility(st), get_debug_text(st), st

        def on_upload_id(file_payload, st: TState):
            path = path_from_gradio_file(file_payload)
            if path:
                st["docs"]["id"]["path"] = path
            st = _invoke(st)
            return render_chat(st["messages"]), *gr_update_visibility(st), get_debug_text(st), st

        def on_satisfied(st: TState):
            extra = feedback_extra_system(st, kind="happy")
            text = ENGINE.contextual_chat(st, extra_system=extra)
            try:
                data_url = image_path_to_data_url(CONGRATS_IMAGE_PATH)
                text += "\n\n" + f"![congrats]({data_url})"
            except Exception:
                pass
            st["messages"].append(("assistant", text))
            st["ui"]["show_satisfaction"] = False
            st["flags"]["last_feedback"] = "happy"
            st["flags"]["reapply_ready"] = False
            return render_chat(st["messages"]), *gr_update_visibility(st), get_debug_text(st), st

        def on_unsatisfied(st: TState):
            extra = feedback_extra_system(st, kind="unhappy")
            text = ENGINE.contextual_chat(st, extra_system=extra)
            st["messages"].append(("assistant", text))
            st["ui"]["show_satisfaction"] = False
            st["flags"]["last_feedback"] = "unhappy"
            st["flags"]["reapply_ready"] = True
            return render_chat(st["messages"]), *gr_update_visibility(st), get_debug_text(st), st

        def on_graph_refresh():
            # render to PIL and return; show a friendly fallback image if rendering not available
            try:
                from ttb_ride.visualize import graph_png
                return graph_png(compiled_graph)
            except Exception as e:
                from PIL import Image, ImageDraw
                img = Image.new("RGB", (980, 260), (255, 255, 255))
                d = ImageDraw.Draw(img)
                d.text(
                    (16, 16),
                    "Graph rendering not available.\n"
                    "Try: pip install 'langgraph[all]'  (or install Graphviz)\n"
                    f"Error: {e}",
                    fill=(0, 0, 0),
                )
                return img


        # Wire events
        user_in.submit(on_user_submit,
                       inputs=[user_in, st],
                       outputs=[chat, up_bike, up_income, up_id, btn_sat, btn_unsat, docs_status, debug_md, st]
                       ).then(_clear_text, None, [user_in])

        up_bike.change(on_upload_bike,     inputs=[up_bike,   st], outputs=[chat, up_bike, up_income, up_id, btn_sat, btn_unsat, docs_status, debug_md, st])
        up_income.change(on_upload_income, inputs=[up_income, st], outputs=[chat, up_bike, up_income, up_id, btn_sat, btn_unsat, docs_status, debug_md, st])
        up_id.change(on_upload_id,         inputs=[up_id,     st], outputs=[chat, up_bike, up_income, up_id, btn_sat, btn_unsat, docs_status, debug_md, st])

        btn_sat.click(   on_satisfied,  inputs=[st], outputs=[chat, up_bike, up_income, up_id, btn_sat, btn_unsat, docs_status, debug_md, st])
        btn_unsat.click( on_unsatisfied, inputs=[st], outputs=[chat, up_bike, up_income, up_id, btn_sat, btn_unsat, docs_status, debug_md, st])
        btn_graph.click(on_graph_refresh, inputs=None, outputs=[graph_img])


    return demo


# ===== bootstrap =====
ENGINE = TtbRideEngine().setup()
set_engine(ENGINE)           # inject into agents module
GRAPH = build_graph()
demo = make_ui(GRAPH)

if __name__ == "__main__":
    demo.launch(server_port=7862, show_error=True)
