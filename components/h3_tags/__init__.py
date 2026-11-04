from comfy_api.latest import io


class H3ReferenceTags(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3ReferenceTags",
            display_name="dharani.prod H3 Reference Tags",
            category="dharani.prod/h3 tags",
            inputs=[
                io.String.Input(
                    "reference_roles",
                    multiline=True,
                    default="",
                    tooltip="One short label per line, in the same order as the reference images connected to your H3 node. These become @image1, @image2, etc.",
                ),
                io.String.Input("prompt", multiline=True, default=""),
            ],
            outputs=[io.String.Output("prompt")],
            description=(
                "Adds your labels to the prompt as @image1, @image2, etc. "
                "Enter one role per line in the same order as the H3 reference images. "
                "This node never reads or describes image content."
            ),
        )

    @classmethod
    def execute(cls, reference_roles, prompt):
        roles = [line.strip() for line in reference_roles.splitlines() if line.strip()]
        if not roles:
            return io.NodeOutput(prompt)

        tags = "\n".join(
            f"@image{index} = {role}"
            for index, role in enumerate(roles, start=1)
        )
        result = tags
        if prompt.strip():
            result += f"\n\n{prompt.strip()}"
        return io.NodeOutput(result)


NODE_CLASS_MAPPINGS = {"H3ReferenceTags": H3ReferenceTags}
NODE_DISPLAY_NAME_MAPPINGS = {"H3ReferenceTags": "H3 Reference Image Tags"}

