"""Estimated editorial pacing; warnings never invent or rewrite scenes."""


def preview_pacing(structure):
    board = getattr(structure, "imported_storyboard", None)
    if not board:
        return None
    offsets, total = [], 0.0
    for block in structure.blocos:
        offsets.append(total)
        total += block.duracao_segundos
    scenes = board["scenes"]
    starts = []
    warnings = []
    motion = {"none": 0, "pan": 0, "zoom": 0}
    for scene in scenes:
        anchor = scene["narration_anchor"]
        block = structure.blocos[anchor["block_order"]]
        starts.append(
            offsets[anchor["block_order"]]
            + block.duracao_segundos * anchor["start_char"] / len(block.conteudo)
        )
        intent = scene["motion_intent"]
        motion["none"] += int(intent == "none")
        motion["pan"] += int(intent.startswith("pan_"))
        motion["zoom"] += int("push_in" in intent or "pull_out" in intent)
        if len(anchor["text"].split()) < 3 or len(anchor["text"].split()) > 80:
            warnings.append(
                f"{scene['id']}: anchor com extensão incomum; revise o trecho selecionado."
            )
    starts[0] = 0.0
    durations = [end - start for start, end in zip(starts, starts[1:] + [total])]
    for scene, duration in zip(scenes, durations):
        if duration < 1.5 or duration > 15:
            warnings.append(
                f"{scene['id']}: imagem estimada por {duration:.1f}s; revise o ritmo."
            )
    if motion["none"] / len(scenes) > 0.5:
        warnings.append("Mais da metade das cenas não usa movimento.")
    return {
        "timing_source": "estimated",
        "average_scene_duration": total / len(scenes),
        "min_scene_duration": min(durations),
        "max_scene_duration": max(durations),
        "motion_distribution": motion,
        "warnings": warnings,
    }
