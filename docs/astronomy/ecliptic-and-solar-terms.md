# Ecliptic frames, tropical zodiac, and solar terms

Part of the [Astronomy Documentation Series](README.md). For engine interfaces, runtime contracts,
and numerical tolerances against JPL Horizons and USNO, see
[Astronomy calculations](calculations.md). For dial stereographic projection and Orloj geometry,
see [Orloj dial foundation](../orloj.md).

This document formally records the exact mathematical identity between the Western tropical zodiac
and the traditional Chinese 24 Solar Terms (二十四節氣) under the Dingqi standard (定氣法),
including the Twelve Solar Stations (十二次), Twelve Monthly Generals (十二月將), stereographic
projection chirality, and seasonal conventions across both Northern and Southern hemispheres. It
provides the theoretical foundation for multi-dial expansion ([Issue #41](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/41))
and zodiac compartment dividers ([Issue #43](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/43)),
fulfilling [Issue #65](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/65).

---

## 1. Astronomical foundation and frame identity

The Western tropical zodiac and the Chinese 24 Solar Terms share an identical physical and
mathematical foundation: the geocentric ecliptic longitude of the Sun, denoted $\lambda_\odot \in [0^\circ, 360^\circ)$.

### The Dingqi standard (定氣法)

Historically, Chinese calendrics employed two distinct methods for defining solar terms:

1. **Pingqi (平氣法, Mean Solar Terms)**: The tropical year was divided into 24 equal intervals of
   time ($\approx 15.218$ days). Because Earth's orbit is elliptical (Kepler's second law), the Sun's
   apparent motion along the ecliptic varies throughout the year (faster near perihelion in January,
   slower near aphelion in July). Pingqi terms therefore drifted from the Sun's true angular positions.
2. **Dingqi (定氣法, True Solar Longitude Terms)**: Proposed by Northern and Southern Dynasties and
   Sui/Tang astronomers (such as Liu Zhuo 劉焯 in the *Huangji Calendar* 皇極曆) and formally adopted
   in the civil calendar during the Ming–Qing transition (the 1645 *Shixian Calendar* 時憲曆,
   formalized in the *Chongzhen Calendar Reform* 《崇禎曆書》 by Xu Guangqi 徐光啟 and Johann Adam
   Schall von Bell 湯若望). Under Dingqi, solar terms are defined strictly by the Sun's geocentric
   ecliptic longitude crossing exact $15^\circ$ multiples:
   $$\lambda_\odot = 15^\circ \times n \quad (n = 0, 1, \dots, 23)$$
   This standard is codified in modern civil astronomy by GB/T 33661-2017 (*Calculation and Promulgation
   of the Chinese Calendar* 《农历的编算和颁行》).

### Shared equinox anchor ($\lambda_\odot = 0^\circ$)

Both systems are dynamically anchored to the astronomical **Vernal Equinox** (春分):
- In Western tropical astrology and horology, $\lambda_\odot = 0^\circ$ defines the ingress of the Sun
  into **Aries (0° ♈)**.
- In Chinese Dingqi astronomy, $\lambda_\odot = 0^\circ$ defines the exact solar term **Chunfen (春分)**.

Because both systems measure angular displacement along the ecliptic eastward from the intersection of
the celestial equator and the ecliptic of date, they are structurally identical:
$$\text{Tropical Sign Index } k = \lfloor \lambda_\odot / 30^\circ \rfloor \quad (k \in \{0, \dots, 11\})$$
$$\text{Solar Term Index } n = \lfloor \lambda_\odot / 15^\circ \rfloor \quad (n \in \{0, \dots, 23\})$$

### Coordinate terminology and the dial contract

In accordance with repository coordinate standards, we distinguish two coordinate frames:
- **Geometric ecliptic longitude of date**: Applies light-time retardation and the IAU 2006
  precession–nutation matrix, but omits annual aberration ($\approx 20.49''$) and gravitational light
  deflection. This is the frame computed by `DialGeometry.sunLongitudeDeg` and plotted by the Orloj dial
  renderer ([`../orloj.md`](../orloj.md)).
- **Apparent ecliptic longitude**: Additionally applies annual aberration and stellar deflection. This
  is the coordinate tabulated in civil ephemerides and almanacs (GB/T 33661-2017).

Because annual aberration shifts ecliptic longitude by at most $\approx 20.5''$ ($\approx 8.2$ minutes of
orbital motion), and because both coordinate definitions anchor at the identical zero point $\lambda_\odot = 0^\circ$
at the equinox crossing, the structural correspondence between tropical signs and Dingqi solar terms holds
identically in both geometric and apparent frames.

---

## 2. Structural mapping: ingresses, midpoints, stations, and generals

The 24 Solar Terms partition the ecliptic into alternating pairs of **Zhongqi (中氣)** and **Jieling (節令)**.
This alternation maps with geometric precision to the compartment layout of astronomical dials:

```text
Ecliptic Longitude:   0°             15°            30°            45°            60°
Zodiac Compartment:   [----------- Aries -----------][---------- Taurus ----------]
Boundary / Centre:    Ingress      Midpoint        Ingress      Midpoint        Ingress
Solar Term Type:      中氣 (Zhongqi) 節令 (Jieling)  中氣 (Zhongqi) 節令 (Jieling)  中氣 (Zhongqi)
Solar Term Name:      春分 (Chunfen) 清明 (Qingming) 穀雨 (Guyu)   立夏 (Lixia)    小滿 (Xiaoman)
Twelve Stations:      [---------- 降婁 -------------][---------- 大梁 ------------]
Monthly General:      戌將 (河魁)                     酉將 (從魁)
Dial Geometry (#43):  Gold Divider  Label Centre    Gold Divider  Label Centre    Gold Divider
```

### 12 中氣 (Zhongqi) as sign ingresses ($30^\circ \times k$)

The 12 Zhongqi sit at exact multiples of $30^\circ$:
$$\lambda_\odot \in \{0^\circ, 30^\circ, 60^\circ, 90^\circ, 120^\circ, 150^\circ, 180^\circ, 210^\circ, 240^\circ, 270^\circ, 300^\circ, 330^\circ\}$$
Every Zhongqi marks the exact celestial ingress of the Sun into a tropical zodiac sign:
- $\lambda_\odot = 0^\circ$ (春分 / Chunfen): Ingress into Aries (白羊宮 ♈)
- $\lambda_\odot = 30^\circ$ (穀雨 / Guyu): Ingress into Taurus (金牛宮 ♉)
- $\lambda_\odot = 60^\circ$ (小滿 / Xiaoman): Ingress into Gemini (雙子宮 ♊)
- $\lambda_\odot = 90^\circ$ (夏至 / Xiazhi): Ingress into Cancer (巨蟹宮 ♋, Summer Solstice)
- $\dots$
- $\lambda_\odot = 270^\circ$ (冬至 / Dongzhi): Ingress into Capricorn (摩羯宮 ♑, Winter Solstice)

On an astronomical clock dial (such as the Orloj ring implemented in #43), the twelve gold dividers spanning
the zodiac band sit at $30^\circ \times k$. Each divider corresponds to the moment the Sun crosses a Zhongqi.

### 12 節令 (Jieling) as compartment midpoints ($30^\circ \times k + 15^\circ$)

The 12 Jieling (or 節氣 in the narrow sense) sit at odd multiples of $15^\circ$:
$$\lambda_\odot \in \{15^\circ, 45^\circ, 75^\circ, 105^\circ, 135^\circ, 165^\circ, 195^\circ, 225^\circ, 255^\circ, 285^\circ, 315^\circ, 345^\circ\}$$
These points lie at the geometric centre of each $30^\circ$ zodiac sign compartment:
- $\lambda_\odot = 15^\circ$ (清明 / Qingming): Aries compartment midpoint (15° ♈)
- $\lambda_\odot = 45^\circ$ (立夏 / Lixia): Taurus compartment midpoint (15° ♉)
- $\dots$
- $\lambda_\odot = 315^\circ$ (立春 / Lichun): Aquarius compartment midpoint (15° ♒)

In [Issue #43](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/43), each zodiac label
(`ARI`, `TAU`, etc.) is placed at `projection.eclipticPoint(index * 30.0 + 15.0)`. That label placement
coincides with the position of the corresponding 節令.

### 12 十二次 (Twelve Solar Stations)

In traditional Chinese astrometry, the ecliptic and equatorial zones were divided into twelve equal
sectors known as the **Twelve Stations (十二次)**:
降婁 (Jianglou), 大梁 (Daliang), 實沈 (Shishen), 鶉首 (Chunshou), 鶉火 (Chunhuo), 鶉尾 (Chunwei),
壽星 (Shouxing), 大火 (Dahuo), 析木 (Ximu), 星紀 (Xingji), 玄枵 (Xuanxiao), 娵訾 (Juzi).

#### Classical definition in *Han Shu* (漢書·律曆志)

In the Han dynasty (*Han Shu* 《漢書·律曆志下》, preserved on [ctext.org](https://ctext.org/han-shu/lv-li-zhi)),
Liu Xin's Santong calendar (三統曆) defined each station by its starting point at a 節令 (*chu* 初),
its midpoint at a 中氣 (*zhong* 中), and its ending boundary (*zhong* 終) across the 28 Lunar Mansions:
- **降婁 (Jianglou)**: 「初奎五度，雨水。中婁四度，春分。終於胃六度。」
- **大梁 (Daliang)**: 「初胃七度，穀雨。中昴八度，清明。終於畢十一度。」
- **實沈 (Shishen)**: 「初畢十二度，立夏。中井初，小滿。終於井十五度。」
- **鶉首 (Chunshou)**: 「初井十六度，芒種。中井三十一度，夏至。終於柳八度。」
- $\dots$
- **星紀 (Xingji)**: 「初斗十二度，大雪。中牽牛初，冬至。終於婺女七度。」
- **玄枵 (Xuanxiao)**: 「初婺女八度，小寒。中危初，大寒。終於危十五度。」
- **娵訾 (Juzi)**: 「初危十六度，立春。中營室初，驚蟄。終於奎四度。」

*(Note: In the Western Han Taichu/Santong calendar, the order of 雨水 and 驚蟄, as well as 穀雨 and 清明,
differed from the Tang and modern Dingqi sequence. The structural principle of pairing each station with one
Jieling and one Zhongqi was already established).*

#### Formalization in *Chongzhen Lishu* (崇禎曆書)

During the late Ming calendar reform, Xu Guangqi and the Jesuit astronomers harmonized the Chinese
Twelve Stations with Western spherical astronomy (*Chongzhen Lishu*, 《恆星經緯表》). Under Dingqi,
the Twelve Stations were formally aligned with the twelve $30^\circ$ tropical zodiac signs:
降婁 $\equiv$ Aries, 大梁 $\equiv$ Taurus, 實沈 $\equiv$ Gemini, 鶉首 $\equiv$ Cancer, 鶉火 $\equiv$ Leo,
鶉尾 $\equiv$ Virgo, 壽星 $\equiv$ Libra, 大火 $\equiv$ Scorpio, 析木 $\equiv$ Sagittarius, 星紀 $\equiv$ Capricorn,
玄枵 $\equiv$ Aquarius, 娵訾 $\equiv$ Pisces.

### 12 月將 (Twelve Monthly Generals) and horological parity

In Chinese astrological horology (*Da Liu Ren* 大六壬 and *Qi Zheng Si Yu* 七政四餘), the astronomical
position of the Sun determines the active **Monthly General (月將)**, also called the Sun's station (日躔所在).
Unlike the civil lunar month (which changes at the new moon / 朔日) or the civil month branch (月建, which
switches at 節令 such as 立春), **the Monthly General switches strictly upon crossing the Zhongqi (過中氣換將)**.

Classical texts on [ctext.org](https://ctext.org) document this strict horological rule:
- ***Ren Xue Suo Ji* 《壬學瑣記》**:
  > 「今時憲書則以定氣為主，故太陽即於交中氣日時過宮，便換月將，此正合天之妙。」
  > *(Now the Shixian calendar is based on Dingqi; thus the Sun enters the new palace precisely at the day and hour of the Zhongqi, whereupon the Monthly General is switched. This is the subtle perfection of aligning with Heaven.)*
- ***Liu Ren Cui Yan* 《六壬粹言》**:
  > 「用月將之法，諸書皆以每月中氣為過宮。每月中氣者，即太陽過宮所躔之辰也。」
  > *(In the method of using the Monthly General, all texts take each month's Zhongqi as the palace crossing. Each month's Zhongqi is precisely the celestial station where the Sun crosses and resides.)*
- ***Liu Ren Jin Jiao Jian* 《六壬金鉸剪》**:
  > 「第一月將，又名太陽……須每月中氣後始過宮。如寅建必須雨水中氣過度後乃以亥為太陽，即月將。」

The 12 Monthly Generals advance through the Earthly Branches in reverse order (亥, 戌, 酉, 申, 未, 午, 巳, 辰, 卯, 寅, 丑, 子),
because the Sun's annual motion along the ecliptic runs opposite to the diurnal rotation of the sky:

| Earthly Branch | Monthly General (月將) | Zhongqi Crossing Point | Tropical Sign Ingress |
| :---: | :---: | :---: | :---: |
| 戌 (Xū) | 河魁 (Hékuí) | 太陽過 **春分** ($\lambda_\odot = 0^\circ$) | Aries (白羊宮 ♈) |
| 酉 (Yǒu) | 從魁 (Cóngkuí) | 太陽過 **穀雨** ($\lambda_\odot = 30^\circ$) | Taurus (金牛宮 ♉) |
| 申 (Shēn) | 傳送 (Chuánsòng) | 太陽過 **小滿** ($\lambda_\odot = 60^\circ$) | Gemini (雙子宮 ♊) |
| 未 (Wèi) | 小吉 (Xiǎojí) | 太陽過 **夏至** ($\lambda_\odot = 90^\circ$) | Cancer (巨蟹宮 ♋) |
| 午 (Wǔ) | 勝光 (Shèngguāng) | 太陽過 **大暑** ($\lambda_\odot = 120^\circ$) | Leo (獅子宮 ♌) |
| 巳 (Sì) | 太乙 (Tàiyǐ) | 太陽過 **處暑** ($\lambda_\odot = 150^\circ$) | Virgo (室女宮 ♍) |
| 辰 (Chén) | 天罡 (Tiāngāng) | 太陽過 **秋分** ($\lambda_\odot = 180^\circ$) | Libra (天秤宮 ♎) |
| 卯 (Mǎo) | 太衝 (Tàichōng) | 太陽過 **霜降** ($\lambda_\odot = 210^\circ$) | Scorpio (天蠍宮 ♏) |
| 寅 (Yín) | 功曹 (Gōngcáo) | 太陽過 **小雪** ($\lambda_\odot = 240^\circ$) | Sagittarius (人馬宮 ♐) |
| 丑 (Chǒu) | 大吉 (Dàjí) | 太陽過 **冬至** ($\lambda_\odot = 270^\circ$) | Capricorn (摩羯宮 ♑) |
| 子 (Zǐ) | 神后 (Shénhòu) | 太陽過 **大寒** ($\lambda_\odot = 300^\circ$) | Aquarius (寶瓶宮 ♒) |
| 亥 (Hài) | 登明 (Dēngmíng) | 太陽過 **雨水** ($\lambda_\odot = 330^\circ$) | Pisces (雙魚宮 ♓) |

This demonstrates that Chinese astrological and horological tradition independently developed a system
strictly identical to Western tropical sign ingress horology: switching the active solar ruler at
$\lambda_\odot = 30^\circ \times k$.

---

## 3. Rigorous comparative reference table

The following reference table maps the full 24 Solar Terms against the Western tropical zodiac signs,
compartment geometry, Twelve Stations, Monthly Generals, and Western astronomical season milestones:

| $\lambda_\odot$ | Type | Solar Term (節氣) | Pinyin / Translation | Tropical Zodiac | Compartment Offset | 十二次 (12 Stations) | 月將 (Monthly General) & Branch | Astronomical Milestone |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| $0^\circ$ | 中氣 | 春分 | Chūnfēn (Vernal Equinox) | Aries (白羊宮 ♈) | Ingress ($0^\circ$) | 降婁 (Jiànglóu) | 河魁 (Hékuí) / 戌 | Vernal Equinox (Spring start) |
| $15^\circ$ | 節令 | 清明 | Qīngmíng (Pure Brightness) | Aries (白羊宮 ♈) | Midpoint ($15^\circ$) | 降婁 (Jiànglóu) | — | Mid-Aries |
| $30^\circ$ | 中氣 | 穀雨 | Gǔyǔ (Grain Rain) | Taurus (金牛宮 ♉) | Ingress ($0^\circ$) | 大梁 (Dàliáng) | 從魁 (Cóngkuí) / 酉 | — |
| $45^\circ$ | 節令 | 立夏 | Lìxià (Beginning of Summer) | Taurus (金牛宮 ♉) | Midpoint ($15^\circ$) | 大梁 (Dàliáng) | — | Mid-Taurus |
| $60^\circ$ | 中氣 | 小滿 | Xiǎomǎn (Grain Buds) | Gemini (雙子宮 ♊) | Ingress ($0^\circ$) | 實沈 (Shíshěn) | 傳送 (Chuánsòng) / 申 | — |
| $75^\circ$ | 節令 | 芒種 | Mángzhòng (Grain in Ear) | Gemini (雙子宮 ♊) | Midpoint ($15^\circ$) | 實沈 (Shíshěn) | — | Mid-Gemini |
| $90^\circ$ | 中氣 | 夏至 | Xiàzhì (Summer Solstice) | Cancer (巨蟹宮 ♋) | Ingress ($0^\circ$) | 鶉首 (Chúnshǒu) | 小吉 (Xiǎojí) / 未 | Summer Solstice (Summer start) |
| $105^\circ$ | 節令 | 小暑 | Xiǎoshǔ (Minor Heat) | Cancer (巨蟹宮 ♋) | Midpoint ($15^\circ$) | 鶉首 (Chúnshǒu) | — | Mid-Cancer |
| $120^\circ$ | 中氣 | 大暑 | Dàshǔ (Major Heat) | Leo (獅子宮 ♌) | Ingress ($0^\circ$) | 鶉火 (Chúnhuǒ) | 勝光 (Shèngguāng) / 午 | — |
| $135^\circ$ | 節令 | 立秋 | Lìqiū (Beginning of Autumn) | Leo (獅子宮 ♌) | Midpoint ($15^\circ$) | 鶉火 (Chúnhuǒ) | — | Mid-Leo |
| $150^\circ$ | 中氣 | 處暑 | Chùshǔ (End of Heat) | Virgo (室女宮 ♍) | Ingress ($0^\circ$) | 鶉尾 (Chúnwěi) | 太乙 (Tàiyǐ) / 巳 | — |
| $165^\circ$ | 節令 | 白露 | Báilù (White Dew) | Virgo (室女宮 ♍) | Midpoint ($15^\circ$) | 鶉尾 (Chúnwěi) | — | Mid-Virgo |
| $180^\circ$ | 中氣 | 秋分 | Qiūfēn (Autumnal Equinox) | Libra (天秤宮 ♎) | Ingress ($0^\circ$) | 壽星 (Shòuxīng) | 天罡 (Tiāngāng) / 辰 | Autumnal Equinox (Autumn start) |
| $195^\circ$ | 節令 | 寒露 | Hánlù (Cold Dew) | Libra (天秤宮 ♎) | Midpoint ($15^\circ$) | 壽星 (Shòuxīng) | — | Mid-Libra |
| $210^\circ$ | 中氣 | 霜降 | Shuāngjiàng (Frost's Descent) | Scorpio (天蠍宮 ♏) | Ingress ($0^\circ$) | 大火 (Dàhuǒ) | 太衝 (Tàichōng) / 卯 | — |
| $225^\circ$ | 節令 | 立冬 | Lìdōng (Beginning of Winter) | Scorpio (天蠍宮 ♏) | Midpoint ($15^\circ$) | 大火 (Dàhuǒ) | — | Mid-Scorpio |
| $240^\circ$ | 中氣 | 小雪 | Xiǎoxuě (Minor Snow) | Sagittarius (人馬宮 ♐) | Ingress ($0^\circ$) | 析木 (Xīmù) | 功曹 (Gōngcáo) / 寅 | — |
| $255^\circ$ | 節令 | 大雪 | Dàxuě (Major Snow) | Sagittarius (人馬宮 ♐) | Midpoint ($15^\circ$) | 析木 (Xīmù) | — | Mid-Sagittarius |
| $270^\circ$ | 中氣 | 冬至 | Dōngzhì (Winter Solstice) | Capricorn (摩羯宮 ♑) | Ingress ($0^\circ$) | 星紀 (Xīngjì) | 大吉 (Dàjí) / 丑 | Winter Solstice (Winter start) |
| $285^\circ$ | 節令 | 小寒 | Xiǎohán (Minor Cold) | Capricorn (摩羯宮 ♑) | Midpoint ($15^\circ$) | 星紀 (Xīngjì) | — | Mid-Capricorn |
| $300^\circ$ | 中氣 | 大寒 | Dàhán (Major Cold) | Aquarius (寶瓶宮 ♒) | Ingress ($0^\circ$) | 玄枵 (Xuánxiāo) | 神后 (Shénhòu) / 子 | — |
| $315^\circ$ | 節令 | 立春 | Lìchūn (Beginning of Spring) | Aquarius (寶瓶宮 ♒) | Midpoint ($15^\circ$) | 玄枵 (Xuánxiāo) | — | Mid-Aquarius |
| $330^\circ$ | 中氣 | 雨水 | Yǔshuǐ (Rain Water) | Pisces (雙魚宮 ♓) | Ingress ($0^\circ$) | 娵訾 (Jūzī) | 登明 (Dēngmíng) / 亥 | — |
| $345^\circ$ | 節令 | 驚蟄 | Jīngzhé (Awakening of Insects) | Pisces (雙魚宮 ♓) | Midpoint ($15^\circ$) | 娵訾 (Jūzī) | — | Mid-Pisces |

---

## 4. Northern vs. Southern Hemisphere duality

### Stereographic projection chirality and handedness

The Orloj astronomical dial employs an astrolabe-style stereographic projection from the celestial pole
above the horizon onto the equatorial plane ([`../orloj.md#projection`](../orloj.md#projection)):
- **Northern plate** (observer latitude $\varphi > 0$): Projected from the North Celestial Pole.
  Cancer ($\delta = +\varepsilon$) forms the outer sky boundary with normalized radius $1.0$, while
  Capricorn ($\delta = -\varepsilon$) forms the inner boundary with radius $\approx 0.43$.
  As sidereal time advances, the sky rotates **clockwise**.
  Because increasing ecliptic longitude $\lambda$ advances eastward against diurnal rotation,
  the sequential signs (`ARI` $\to$ `TAU` $\to$ `GEM` $\dots$) run **counter-clockwise** around the dial face:
  - $\lambda = 0^\circ$ (Aries): Top of dial ($12\text{ o'clock}$, $x = 0, y < 0$)
  - $\lambda = 90^\circ$ (Cancer): Left of dial ($9\text{ o'clock}$, $x < 0, y = 0$)
  - $\lambda = 180^\circ$ (Libra): Bottom of dial ($6\text{ o'clock}$, $x = 0, y > 0$)
  - $\lambda = 270^\circ$ (Capricorn): Right of dial ($3\text{ o'clock}$, $x > 0, y = 0$)
- **Southern plate** (observer latitude $\varphi < 0$): Projected from the South Celestial Pole.
  The south-pole plate is the **equatorial radial inversion** of the north-pole plate:
  Capricorn ($\delta = -\varepsilon$) swaps to the outer boundary (radius $1.0$), and Cancer ($\delta = +\varepsilon$)
  becomes the inner boundary (radius $\approx 0.43$).
  The entire zodiac ring is **point-reflected** through the dial origin ($x \to -x, y \to -y$):
  $$\text{south.eclipticPoint}(\lambda) = -\text{north.eclipticPoint}(\lambda + 180^\circ)$$
  This transformation preserves the sign ordering along the ring while swapping the inner and outer
  tropic radii.

### Celestial invariance vs. ecological opposition

A fundamental distinction must be maintained between celestial coordinates and terrestrial phenology:
- **Celestial Invariance**: The 24 Solar Terms are universal geocentric coordinates $\lambda_\odot$.
  The Sun reaches $\lambda_\odot = 270^\circ$ at the exact same physical instant for observers in Beijing,
  Prague, Sydney, or the South Pole. Astronomical instruments, ephemerides, and horological dials must
  treat $\lambda_\odot$ as an invariant physical coordinate.
- **Ecological Opposition**: The phenomenological names of the terms (e.g., 霜降 / Frost's Descent,
  小雪 / Minor Snow, 大暑 / Major Heat) originated in the temperate climate of the Yellow River basin
  (中原地區, $\approx 35^\circ\text{N}$). When the Sun reaches $\lambda_\odot = 270^\circ$ (冬至 / Dongzhi):
  - In the Northern Hemisphere, it is astronomical midwinter (minimum solar altitude, shortest daylight).
  - In the Southern Hemisphere, it is astronomical midsummer (maximum solar altitude, longest daylight).
  Similarly, at $\lambda_\odot = 90^\circ$ (夏至 / Xiazhi), the Southern Hemisphere experiences midwinter.

While cultural practitioners in the Southern Hemisphere occasionally debate inverted calendar terms
(e.g., using "Midsummer" at $\lambda_\odot = 270^\circ$), astronomical clocks and dials display **celestial positions**,
not local weather. The Sun at $\lambda_\odot = 270^\circ$ is astronomically at 0° Capricorn and Dongzhi
globally; its physical dial position is governed by invariant celestial mechanics.

### Astrological neutrality of 十二次 (Twelve Solar Stations)

Unlike the 24 Solar Terms, whose weather-derived names create ecological cognitive dissonance in the
Southern Hemisphere, the **Twelve Solar Stations (十二次)** are inherently neutral:
- The station names are based on ancient star groupings and celestial asterisms:
  - **星紀 (Xingji)**: Derived from the Southern Dipper (斗) and Ox (牛) asterisms.
  - **玄枵 (Xuanxiao)**: Derived from the Void (虛) and Rooftop (危) asterisms.
  - **娵訾 (Juzi)**: Derived from the Encampment (室) and Wall (壁) asterisms.
  - **降婁 (Jianglou)**: Derived from the Legs (奎) and Bond (婁) asterisms.
  - **大梁 (Daliang)**: Derived from the Pleiades (昴) and Net (畢).
  - **實沈 (Shishen)**: Named after the mythological astral spirit of Orion (參).
  - **鶉首, 鶉火, 鶉尾 (Chunshou, Chunhuo, Chunwei)**: The Head, Fire, and Tail of the Quail (Vermilion Bird of the South).
  - **壽星 (Shouxing)**: Named after the Horn (角) and Neck (亢) asterisms.
  - **大火 (Dahuo)**: Named after Antares in the Heart (心) asterism.
  - **析木 (Ximu)**: Derived from the Tail (尾) and Winnowing Basket (箕) dividing the Milky Way.
- None of the Twelve Stations refer to seasonal temperature, freezing, agriculture, or precipitation.
  Consequently, they serve as completely neutral astronomical sector designations, equally valid and
  accurate in both the Northern and Southern hemispheres.

### Precession immunity

In ancient Chinese astronomy prior to the Jin dynasty (when Yu Xi 虞喜 discovered axial precession 歲差),
the equatorial 28 Lunar Mansions (二十八宿) were assumed to be fixed with respect to the solstices.
Over centuries, precession caused the equinoxes to drift through the mansions by $\approx 50.29''/\text{year}$
($\approx 1^\circ$ every $71.6$ years). Since Liu Xin codified the *Santong Calendar* in the Han dynasty
($\approx 2000$ years ago), the equinox has drifted by nearly $30^\circ$ relative to the 28 Mansions
(moving from the Legs/Bond 奎/婁 asterisms toward the Wall/Encampment 壁/室 asterisms).

In sharp contrast:
- Both the **Western tropical zodiac** and the **Dingqi 24 Solar Terms** are dynamically anchored to
  the true vernal equinox ($\lambda_\odot = 0^\circ$).
- Because both systems share the same moving dynamical equinox of date, **they co-precess perfectly**.
- The mathematical equivalence between Chunfen and 0° Aries, Xiazhi and 0° Cancer, Qiufen and 0° Libra,
  and Dongzhi and 0° Capricorn is **precession-invariant**: it will remain exact for all epochs,
  past, present, and future.
