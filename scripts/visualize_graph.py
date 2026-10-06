from app.services.agent_graph import custom_graph, prebuilt_graph

def draw_mermaind(name: str, graph):


    mermaid=graph.get_graph().draw_mermaid()
    mermaid_png=graph.get_graph().draw_mermaid_png()

    print(mermaid)

    with open(f"docs/{name}.mmd", "w") as fh:
        fh.write(mermaid)
    with open(f"docs/{name}.png", "wb") as fh:
        fh.write(mermaid_png)

draw_mermaind("custom_graph", custom_graph)
draw_mermaind("prebuilt_graph", prebuilt_graph)
