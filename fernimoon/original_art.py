"""Original noir-style reconstructions of a *reported* urban legend.

These are NOT evidence or authentic footage. No copyrighted movie characters,
third-party photographs, or AI image generation are required.
"""
import math
import random
import re
from pathlib import Path


LEGEND_REFERENCES = [
    {
        "title": "PBS Monstrum: Don't Let Them In! The Urban Legends of Black-Eyed Children",
        "url": "https://www.pbs.org/video/dont-let-them-in-the-urban-legends-of-black-eyed-children-oht8de/",
        "note": "Folklore analysis of a reported encounter, not corroborating evidence."
    },
    {
        "title": "USC Digital Folklore Archives: Black Eyed Children",
        "url": "https://folklore.usc.edu/black-eyed-children/",
        "note": "Folklore archive identifying this as a contemporary urban legend."
    },
]


def is_black_eyed_children(topic: str) -> bool:
    words = set(re.findall(r"[a-z]+", topic.casefold()))
    return {"black", "eyed"} <= words and bool({"children", "child", "kids", "kid"} & words)


def generate_reconstruction(work: Path) -> list[dict]:
    """Render six distinct licensed-to-use original illustrations with Pillow."""
    from PIL import Image, ImageDraw, ImageFilter

    width, height = 720, 1280
    titles = [
        "A deserted Texas parking lot at night, theatrical reconstruction",
        "Two child silhouettes approach the driver's car window, theatrical reconstruction",
        "A hand touches the glass while two children stand outside, theatrical reconstruction",
        "Entirely black eyes seen in a fearful imagined close-up, theatrical reconstruction",
        "A 1990s-style computer represents the legend circulating online, theatrical reconstruction",
        "A car leaving the empty parking lot, theatrical reconstruction",
    ]

    def glow(canvas, x, y, rad, color, intensity=125):
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.ellipse((x-rad, y-rad, x+rad, y+rad), fill=(*color, intensity))
        canvas.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(max(5, rad//3))))

    def child(draw, x, y, scale=1.0, show_eyes=True):
        """Graphic silhouettes, not portraits of actual children."""
        s = scale
        skin = (139, 145, 148, 255)
        coat = (20, 26, 37, 255)
        draw.polygon([(x-63*s,y+175*s),(x-55*s,y+59*s),(x-33*s,y+18*s),
                      (x+29*s,y+18*s),(x+52*s,y+56*s),(x+71*s,y+175*s)], fill=coat)
        draw.ellipse((x-35*s,y-46*s,x+35*s,y+45*s), fill=skin)
        draw.arc((x-37*s,y-52*s,x+37*s,y+25*s),175,350,fill=(10,15,23,255),width=max(2,int(18*s)))
        if show_eyes:
            for dx in (-15, 15):
                draw.ellipse((x+(dx-7)*s,y-11*s,x+(dx+7)*s,y+3*s),fill=(0,0,3,255))
        draw.line([(x-55*s,y+62*s),(x-80*s,y+141*s)],fill=coat,width=max(3,int(18*s)))

    for index, title in enumerate(titles):
        im = Image.new("RGBA", (width, height), (0,0,0,255))
        d = ImageDraw.Draw(im)
        tints = [(9,15,27), (7,15,27), (8,13,23), (11,13,20),
                 (8,19,23), (9,14,25)]
        r0, g0, b0 = tints[index]
        for y in range(height):
            pct = y / height
            d.line((0,y,width,y), fill=(int(r0+10*pct), int(g0+14*pct),
                                        int(b0+18*pct),255))
        randomizer = random.Random(20261107 + index)
        # Atmospheric streetlamp or dashboard reflections.
        if index in (0,1,2,5):
            glow(im, 510, 265, 180, (225,165,83), 90)
            d = ImageDraw.Draw(im)
            d.line((510, 285, 507, 1070), fill=(69,67,69,255), width=9)
            d.ellipse((493,245,524,277),fill=(230,194,123,255))
            d.polygon([(500,290),(525,290),(720,1030),(100,1050)],fill=(53,39,31,45))
        if index==0:
            d=ImageDraw.Draw(im)
            # Asphalt receding into the fog, outlines of empty parking spaces.
            d.polygon([(0,850),(720,810),(720,1280),(0,1280)],fill=(24,29,35,255))
            for k in range(4):
                y=925+k*84
                d.line((30,y,200+k*110,y-15), fill=(79,82,82,255),width=4)
            d.rounded_rectangle((145,768,568,991),radius=23,fill=(14,19,30,255))
            d.polygon([(205,775),(430,775),(486,866),(155,865)],fill=(45,52,63,255))
            d.ellipse((185,936,275,1014), fill=(7,9,16,255))
            d.ellipse((448,933,538,1013), fill=(7,9,16,255))
            glow(im,135,880,55,(247,210,135),200)
        elif index==1:
            d=ImageDraw.Draw(im)
            # POV inside a parked car: edge of windshield and door frame.
            d.polygon([(0,0),(82,0),(128,1280),(0,1280)],fill=(8,9,14,255))
            d.line((50,160,155,1280),fill=(47,50,55,255),width=23)
            child(d,320,597,1.3)
            child(d,540,610,1.0)
            d.polygon([(0,1030),(720,1045),(720,1280),(0,1280)],fill=(12,14,23,255))
            d.arc((170,1090,505,1370),190,344,fill=(55,62,70,255),width=27)
        elif index==2:
            d=ImageDraw.Draw(im)
            child(d,330,574,1.7)
            child(d,570,655,1.0)
            d.line((50,0,50,1280),fill=(84,103,114,255),width=24)
            d.line((40,1040,720,1040),fill=(62,79,88,255),width=19)
            # A raised palm at the glass, drawn without suggesting real footage.
            d.ellipse((120,660,210,783), fill=(119,123,125,255))
            for k in range(4):
                xx=123+20*k
                d.line((xx,711,xx+2,622+10*k),fill=(114,118,121,255),width=12)
            for k in range(9):
                y=140+k*110
                d.line((55,y,65+randomizer.randint(-20,90),y+45),fill=(88,95,102,75),width=2)
        elif index==3:
            d=ImageDraw.Draw(im)
            glow(im,360,540,360,(107,132,147),72)
            d=ImageDraw.Draw(im)
            d.ellipse((95,305,630,989),fill=(117,131,135,255))
            d.pieslice((78,255,645,850),185,355,fill=(19,25,32,255))
            d.ellipse((145,555,309,676),fill=(7,8,12,255))
            d.ellipse((423,553,584,675),fill=(7,8,12,255))
            d.arc((267,748,468,830),8,170,fill=(45,41,49,255),width=7)
            d.line((55,0,80,1280),fill=(41,54,66,130),width=19)
        elif index==4:
            d=ImageDraw.Draw(im)
            glow(im,360,600,290,(92,194,186),75)
            d=ImageDraw.Draw(im)
            d.rounded_rectangle((85,375,635,895),radius=24,
                                fill=(118,123,115,255))
            d.rectangle((119,410,601,783),fill=(5,35,38,255))
            for k in range(14):
                yy=453+k*23
                d.rectangle((151,yy,151+randomizer.randint(105,390),yy+5),
                            fill=(88,152,139,255))
            d.polygon([(210,895),(500,895),(580,986),(128,986)],fill=(92,98,101,255))
            d.line((128,986,580,986),fill=(33,46,50,255),width=17)
        else:
            d=ImageDraw.Draw(im)
            # View from within a moving car after the alleged encounter.
            d.polygon([(0,660),(720,660),(720,1280),(0,1280)],fill=(17,26,35,255))
            d.polygon([(290,700),(440,700),(720,1280),(0,1280)],fill=(27,31,38,255))
            for k in range(8):
                yy=758+k*68
                d.line((360,yy,363,yy+24),fill=(143,125,91,255),width=7)
            d.rounded_rectangle((132,205,574,520),radius=33,fill=(60,67,75,255))
            d.rounded_rectangle((147,225,558,499),radius=30,fill=(31,39,46,255))
            child(d,262,337,0.48)
            child(d,421,352,0.46)
            d.arc((145,1070,600,1420),185,355,fill=(84,95,104,255),width=40)
        # Sparse drifting rain/dust is illustrated, not recorded.
        d = ImageDraw.Draw(im)
        for k in range(165):
            xx=randomizer.randrange(width)
            yy=randomizer.randrange(height)
            fade=randomizer.randrange(26,67)
            d.line((xx,yy,xx-3,yy+randomizer.randrange(5,22)),
                   fill=(130,153,164,fade), width=1)
        # A subtle dark vignette ties together all six pictures.
        vignette=Image.new("RGBA",(width,height),(0,0,0,0))
        vd=ImageDraw.Draw(vignette)
        for k in range(0,140,7):
            vd.rounded_rectangle((k,k,width-k,height-k),radius=40,
                                 outline=(0,0,0,max(2,int(16*(1-k/140)))),width=11)
        im.alpha_composite(vignette)
        path = work / f"reconstruction-{index:02d}.png"
        im.convert("RGB").save(path, optimize=True)

    return [
        {
            "id": f"R{i+1}", "kind": "illustration", "file": f"reconstruction-{i:02d}.png",
            "title": title, "source": "FERNIMOON original artwork",
            "creator": "FERNIMOON STUDIO", "license": "Original illustration",
            "license_url": "", "page_url": "", "source_description":
                "Original dramatized illustration of an unverified modern urban legend. Not an eyewitness photograph.",
            "event_match": True, "priority_tier": 3,
            "authenticity": "fictional_reconstruction_not_archival_evidence",
            "visual_review": "Purpose-built original scene; clearly labeled dramatization."
        }
        for i, title in enumerate(titles)
    ]
