"""Potong klip vertikal 9:16 dengan subtitle yang dibakar ke video."""
from .common import run
from .subtitles import srt_for_clip


def render_clip(media, transcript, clip, out_dir, index, font="Arial"):
    stem = f"clip_{index:02d}"
    srt_name = f"{stem}.srt"
    out_name = f"{stem}.mp4"
    srt_for_clip(transcript, clip["start"], clip["end"], out_dir / srt_name)

    style = (f"FontName={font},FontSize=10,Bold=1,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=55")
    vf = f"crop='min(iw,ih*9/16)':ih,scale=1080:1920,subtitles={srt_name}:force_style='{style}'"
    # Satuan style subtitle = skala libass (tinggi 288), bukan piksel: FontSize=10 ~ 67 px di video 1920 px.
    # cwd = folder output, jadi nama file SRT cukup relatif (menghindari masalah path Windows di filter).
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-ss", f"{clip['start']:.2f}", "-i", media, "-t", f"{clip['end'] - clip['start']:.2f}",
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", out_name], cwd=out_dir)
    return out_dir / out_name
