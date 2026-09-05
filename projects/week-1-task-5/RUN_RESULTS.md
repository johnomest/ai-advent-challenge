# Неделя 1, задание 5: результаты запуска

Дата запуска: 5 сентября 2026 года.

Один аналитический запрос отправлен трём конфигурациям DeepSeek и трём бесплатным моделям OpenCode Zen. Для всех вариантов использованы одинаковые условие задачи, системная инструкция и лимит ответа.

## Сводные метрики

| Уровень | Провайдер | Модель | Время | Всего токенов | Reasoning | Стоимость | Завершение |
|---|---|---|---:|---:|---:|---:|---|
| Слабая | DeepSeek | `deepseek-v4-flash` | 6,22 с | 1 522 | 0 | $0,001454 | stop |
| Средняя | DeepSeek | `deepseek-v4-flash` | 23,59 с | 4 034 | 3 051 | $0,004770 | stop |
| Сильная | DeepSeek | `deepseek-v4-pro` | 136,06 с | 8 537 | 8 000 | $0,031736 | length |
| Zen слабая | OpenCode Zen | `nemotron-3.5-lightning-free` | 175,47 с | 8 504 | 5 576 | $0 | length |
| Zen средняя | OpenCode Zen | `mimo-v2.5-free` | 59,59 с | 5 572 | 0 | $0 | stop |
| Zen сильная | OpenCode Zen | `nemotron-3-ultra-free` | 127,41 с | 5 539 | 3 155 | $0 | stop |

Общая стоимость платных запросов DeepSeek: **$0,037960**. Запросы OpenCode Zen выполнены бесплатно.

## Краткий вывод

- Слабая конфигурация DeepSeek завершила ответ, но решила задачу неверно.
- Средняя конфигурация DeepSeek дала правильный результат и хороший баланс скорости и стоимости.
- Сильная конфигурация DeepSeek исчерпала лимит в 8 000 output-токенов и не сформировала финальный ответ.
- Слабая Zen-модель нашла правильное распределение во внутренних рассуждениях, но её финальный ответ также оборвался по лимиту.
- Средняя Zen-модель дала полный правильный ответ быстрее остальных бесплатных вариантов.
- Сильная Zen-модель дала правильный компактный ответ, но работала более чем вдвое дольше средней.

Лучший результат среди платных конфигураций: **DeepSeek Flash с thinking `low`**. Лучший бесплатный результат: **`mimo-v2.5-free`**.

## Полные ответы моделей

### СЛАБАЯ: DeepSeek / deepseek-v4-flash
##### 1. Распределение блоков
Всего **15 блоков** (по $1,000). С учётом минимумов: A≥1, B≥1, C≥1. Максимумы: A≤8, B≤7, C≤6.

Оптимальное распределение (максимизация ожидаемой чистой прибыли):
- **A: 3 блока** (предельная отдача 450/1000)
- **B: 7 блоков** (первые 3 по 600, следующие 4 по 180, но с ожиданием 0.8*600=480, 0.8*180=144)
- **C: 5 блоков** (первые 2 по 750, следующие 3 по 250)

Проверка: 3+7+5 = 15.
Предельные отдачи на последний блок: A(4-й)=220, B(7-й)=180*0.8=144, C(6-й)=250 – поэтому выгоднее держать C, чем добавлять A/B.

##### 2. Расчёт по каналам
Ожидаемые слушатели:
- **A**: 3×450 = **1,350** (все в высокой зоне)
- **B**: 7 блоков → 3×600 + 4×180 = 1,800 + 720 = 2,520. Ожидание: 0.8×2,520 = **2,016**
- **C**: 5 блоков → 2×750 + 3×250 = 1,500 + 750 = **2,250** (без риска)

Валовая маржа (по $4 за слушателя):
- A: 1,350×4 = $5,400
- B: 2,016×4 = $8,064
- C: 2,250×4 = $9,000

Затраты: A $3,000, B $7,000, C $5,000.
Чистая прибыль:
- A: 5,400 – 3,000 = **$2,400**
- B: 8,064 – 7,000 = **$1,064**
- C: 9,000 – 5,000 = **$4,000**

##### 3. Таблица

| Канал | Блоки | Ожид. слушатели | Валовая маржа | Чистая прибыль |
|-------|-------|-----------------|---------------|----------------|
| A     | 3     | 1,350           | $5,400        | $2,400         |
| B     | 7     | 2,016           | $8,064        | $1,064         |
| C     | 5     | 2,250           | $9,000        | $4,000         |
| **Итого** | **15** | **5,616**       | **$22,464**   | **$7,464**     |

**Худший сценарий (B даёт 50%)**: фактически B слушатели = 2,520×0.5 = 1,260, вал. маржа = $5,040, чистая = –$1,960.
Итого: A $2,400 + B –$1,960 + C $4,000 = **$4,440**. Ожидаемое значение (80% полный, 20% худший): 0.8×$7,464 + 0.2×$4,440 = $5,971.2 + $888 = **$6,859.2** – но для обязательного полного расхода бюджет фиксирован, поэтому прибыль варьируется.

##### 4. Итог и обоснование
Оптимум достигнут приравниванием **ожидаемой предельной прибыли** (маржи × вероятность / затраты) на последний блок:
- A 3-й блок: 450×4 / 1,000 = $1.80
- B 7-й блок: 0.8×180×4 / 1,000 = $0.576
- C 5-й блок: 250×4 / 1,000 = $1.00

Дальнейшее перераспределение (например, перенос из C в A или B) снизит суммарную прибыль, т.к. C имеет более высокую предельную отдачу на 6-й блок (250), чем A (220) или B (144 ожидаемых). Минимумы также соблюдены.

**Общий итог**: при обязательном расходе $15,000 максимальная ожидаемая чистая прибыль = **$7,464**.

> **Метрики:** 6.22 с; input=445 (cache hit=384, miss=61); output=1077; reasoning=0; total=1522; peak; cost=$0.001454; finish=stop

### СРЕДНЯЯ: DeepSeek / deepseek-v4-flash
##### Распределение бюджета

Всего 15 блоков по $1,000. Выбраны блоки с максимальной ожидаемой предельной маржой.

| Канал | Блоки | Ожидаемые слушатели | Валовая маржа ($) | Чистая прибыль ($) |
|-------|-------|---------------------|-------------------|---------------------|
| A     | 6     | 2240                | 8 960             | 2 960               |
| B     | 3     | 1620                | 6 480             | 3 480               |
| C     | 6     | 2500                | 10 000            | 4 000               |
| **Итого** | **15** | **6360**         | **25 440**        | **10 440**          |

Затраты: 15 × $1 000 = $15 000.
Ожидаемая чистая прибыль = $25 440 − $15 000 = **$10 440**.

##### Худший сценарий (B даёт 50% результата)

- B: 3 блока × 600 × 0,5 = 900 слушателей → маржа $3 600.
- Общая валовая маржа = $8 960 + $3 600 + $10 000 = $22 560.
- Чистая прибыль = $22 560 − $15 000 = **$7 560**.

##### Оптимальность

Маржинальность (ожидаемая валовая маржа на блок):
C (1–2) = $3 000, B (1–3) = $2 160, A (1–4) = $1 800, C (3–6) = $1 000, A (5–8) = $880, B (4–7) = $648.

Взяты все блоки с маржой ≥ $880 (включая A5–A6). Последний взятый блок — A6 ($880), а следующие доступные (A7, A8, B4) имеют маржу не выше, чем уже включённые. Поэтому распределение максимизирует сумму при жёстких ограничениях бюджета и минимумах по каналам.

> **Метрики:** 23.59 с; input=445 (cache hit=384, miss=61); output=3589; reasoning=3051; total=4034; peak; cost=$0.004770; finish=stop

### СИЛЬНАЯ: DeepSeek / deepseek-v4-pro
[Финальный ответ не сформирован]

> **Метрики:** 136.06 с; input=537 (cache hit=512, miss=25); output=8000; reasoning=8000; total=8537; peak; cost=$0.031736; finish=length

### ZEN СЛАБАЯ: OpenCode Zen / nemotron-3.5-lightning-free
Here's a thinking process:

1.  **Understand the Goal**:
   - Total budget: $15,000, blocks of $1,000 each → 15 blocks total.
   - Minimum 1 block per channel, max: A=8, B=7, C=6.
   - Need to allocate 15 blocks across A, B, C respecting these constraints.
   - Goal: Maximize expected net profit.
   - Revenue per new listener: $4 gross margin before ad costs.
   - Ad costs are already sunk (budget spent), so net profit = (expected listeners * $4) - $15,000.
   - Actually, since $15,000 is fixed spent, maximizing expected net profit ⇔ maximizing expected total listeners * $4.
   - Wait, need to check: "Each new listener brings $4 expected gross margin before advertising expenses." So gross margin = listeners * 4. Net profit = gross margin - ad spend. Since ad spend is fixed at $15,000, maximizing net profit is equivalent to maximizing expected listeners. But I'll keep the calculation explicit: Net Profit = ExpectedListeners * 4 - 15000.

2.  **Analyze Diminishing Returns (Marginal Gains per Block)**:
   - Channel A:
     - Blocks 1-4: +450 each
     - Blocks 5-8: +220 each
   - Channel B:
     - Blocks 1-3: +600 each
     - Blocks 4-7: +180 each
     - But B has 20% chance of 50% result, 80% chance of full result. So expected marginal gain per block for B needs adjustment. Actually, the probability applies to the whole channel result or per block? "Для канала B существует вероятность 20%, что он даст только 50% заявленного результата; в остальных 80% он даст полный результат." This likely means the entire channel's output is scaled, or per block? Typically in such problems, it's the overall channel effectiveness. But it says "For the main calculation use mathematical expectation." I'll assume the 50%/80% applies to the total expected listeners from B, or perhaps per block? To be safe, I'll treat it as: each block's announced result for B is multiplied by 0.8 (full) + 0.2 * 0.5 = 0.9 expected factor. So expected marginal listeners for B = announced * 0.9. I'll clarify this in the calculation. Actually, re-read: "Для канала B существует вероятность 20%, что он даст только 50% заявленного результата; в остальных 80% он даст полный результат." This could mean if we allocate x blocks to B, the actual listeners are either 0.5 * announced or 1.0 * announced. So expected listeners = 0.8 * announced + 0.2 * (0.5 * announced) = 0.9 * announced. I'll apply this to the total expected listeners from B, or equivalently to each block's marginal gain since it's linear. I'll assume per-block expected gain = 0.9 * announced marginal.

   - Channel C:
     - Blocks 1-2: +750 each
     - Blocks 3-6: +250 each

3.  **Constraints**:
   - Total blocks = 15
   - A ∈ [1,8], B ∈ [1,7], C ∈ [1,6]
   - Sum = 15

4.  **Objective**: Maximize expected total listeners * 4 - 15000. Since *4 - 15000 is constant shift, maximize expected total listeners.

   Let's list marginal expected listeners per block (after B's expectation factor 0.9):
   - A:
     Block 1: 450
     Block 2: 450
     Block 3: 450
     Block 4: 450
     Block 5: 220
     Block 6: 220
     Block 7: 220
     Block 8: 220
   - B (expected = 0.9 * announced):
     Block 1: 600 * 0.9 = 540
     Block 2: 600 * 0.9 = 540
     Block 3: 600 * 0.9 = 540
     Block 4: 180 * 0.9 = 162
     Block 5: 162
     Block 6: 162
     Block 7: 162
   - C:
     Block 1: 750
     Block 2: 750
     Block 3: 250
     Block 4: 250
     Block 5: 250
     Block 6: 250

   Now, I need to pick 15 blocks total, at least 1 each, respecting maxes, to maximize sum of marginal gains.

   This is a classic greedy allocation problem with diminishing returns and caps. Since all marginal gains are positive, we want to pick the highest marginal blocks first, subject to channel caps and min constraints.

   Let's sort all possible blocks by marginal expected listeners:
   - C1: 750
   - C2: 750
   - A1: 450
   - A2: 450
   - A3: 450
   - A4: 450
   - B1: 540 (wait, 540 > 450, so B1 should be higher than A1)
   Let's re-sort properly:
   C1: 750
   C2: 750
   B1: 540
   B2: 540
   B3: 540
   A1: 450
   A2: 450
   A3: 450
   A4: 450
   C3: 250
   C4: 250
   C5: 250
   C6: 250
   A5: 220
   A6: 220
   A7: 220
   A8: 220
   B4: 162
   B5: 162
   B6: 162
   B7: 162

   Wait, check B3 vs A4: B3=540, A4=450, correct.
   Now, we must allocate at least 1 block to each channel. So we start with A1, B1, C1. That's 3 blocks. Remaining 12 blocks to allocate from the pool, but we can also add more to any channel up to max.

   Let's do greedy: Start with minimum 1 each: A=1, B=1, C=1. Total=3. Remaining=12.
   Now, consider next best block available without exceeding maxes.
   Current available next blocks:
   A: can go up to 8, next is A2 (450)
   B: can go up to 7, next is B2 (540)
   C: can go up to 6, next is C2 (750)
   So we pick C2. Now C=2, total=4, remaining=11.
   Next: C max is 6, so C3 is 250. A2=450, B2=540. Best is B2 (540). Pick B2. B=2, total=5, remaining=10.
   Next: A2=450, B3=540, C3=250. Best B3. Pick B3. B=3, total=6, remaining=9.
   Next: A2=450, B4=162, C3=250. Best A2 (450). Pick A2. A=2, total=7, remaining=8.
   Next: A3=450, B4=162, C3=250. Best A3. Pick A3. A=3, total=8, remaining=7.
   Next: A4=450, B4=162, C3=250. Best A4. Pick A4. A=4, total=9, remaining=6.
   Now A has used 4 blocks (its first phase). Next A5=220.
   Next: A5=220, B4=162, C3=250. Best C3 (250). Pick C3. C=3, total=10, remaining=5.
   Next: A5=220, B4=162, C4=250. Best C4 (250). Pick C4. C=4, total=11, remaining=4.
   Next: A5=220, B4=162, C5=250. Best C5 (250). Pick C5. C=5, total=12, remaining=3.
   Next: A5=220, B4=162, C6=250. Best C6 (250). Pick C6. C=6, total=13, remaining=2.
   Now C is at max 6.
   Next: A5=220, B4=162. Best A5 (220). Pick A5. A=5, total=14, remaining=1.
   Next: A6=220, B4=162. Best A6 (220). Pick A6. A=6, total=15, remaining=0.

   Let's check the allocation: A=6, B=3, C=6. Sum=15.
   Check constraints: A ∈ [1,8] ok (6). B ∈ [1,7] ok (3). C ∈ [1,6] ok (6). Min 1 each ok.
   Let's verify if this is indeed optimal. I followed greedy by marginal expected gain. Since all marginal gains are decreasing within each channel (non-increasing), and we have a knapsack with cardinality constraint and individual caps, greedy by marginal benefit works if the marginal functions are concave (diminishing returns), which they are. But I should double-check if any alternative could beat it.

   Let's list the chosen blocks and their gains:
   A: blocks 1-6. Gains: 450*4 + 220*2 = 1800 + 440 = 2240 expected listeners.
   B: blocks 1-3. Gains: 540*3 = 1620 expected listeners.
   C: blocks 1-6. Gains: 750*2 + 250*4 = 1500 + 1000 = 2500 expected listeners.
   Total expected listeners = 2240 + 1620 + 2500 = 6360.

   Let's test if reallocating one block from A to B or C could increase. Currently A has 6, B has 3, C has 6.
   What if we reduce A by 1 (lose A6=220), and increase B by 1 (gain B4=162) -> net -58. Bad.
   Increase C by 1 but C is at max 6, can't.
   Reduce A by 2, increase B by 2: lose A5+A6=440, gain B4+B5=324 -> -116.
   Reduce A by 1, increase B by 1 and C? C maxed.
   What about shifting from C to somewhere? C6=250, if we take from C, lose 250, can add to A or B. A max 8, we have A=6, could add A7=220 or A8=220. B could go up to 7, we have B=3, could add B4=162, B5=162, etc. Clearly 250 > 220 > 162, so keeping C maxed is good.
   What about B? B has diminishing: 1-3 are 540 each, 4-7 are 162. So 3 blocks give 1620. If we could get 4 blocks, it's 1620+324=1944, but we'd need to take 2 blocks from somewhere. Currently we have A=6, C=6. If we reduce A to 4 and C to 4, we free 2 blocks, could add B4 and B5, but lose A5+A6=440 and C5+C6=500, net loss. So B staying at 3 seems optimal.

   Let's double-check the greedy sequence and totals carefully.

   Allocation: A=6, B=3, C=6. Sum=15.
   Let's compute expected listeners precisely:
   A: blocks 1-4: 450 each = 1800. Blocks 5-6: 220 each = 440. Total A = 2240.
   B: blocks 1-3: expected 540 each = 1620. (Since 0.9*600=540)
   C: blocks 1-2: 750 each = 1500. Blocks 3-6: 250 each = 1000. Total C = 2500.
   Sum = 2240 + 1620 + 2500 = 6360.

   Now, check if any other combination gives >6360.
   Let's systematically consider the marginal ranking and the constraint that we must pick exactly 15 blocks, at least 1 each, maxes.
   The sorted list of all 8+7+6=21 blocks by expected gain:
   C1: 750
   C2: 750
   B1: 540
   B2: 540
   B3: 540
   A1: 450
   A2: 450
   A3: 450
   A4: 450
   A5: 220
   A6: 220
   A7: 220
   A8: 220
   C3: 250
   C4: 250
   C5: 250
   C6: 250
   B4: 162
   B5: 162
   B6: 162
   B7: 162

   Wait, I need to re-sort correctly because C3-C6 are 250, which is higher than A5-A8 (220) and B4-B7 (162). So the full sorted order:
   1: C1 750
   2: C2 750
   3: B1 540
   4: B2 540
   5: B3 540
   6: A1 450
   7: A2 450
   8: A3 450
   9: A4 450
   10: C3 250
   11: C4 250
   12: C5 250
   13: C6 250
   14: A5 220
   15: A6 220
   16: A7 220
   17: A8 220
   18: B4 162
   19: B5 162
   20: B6 162
   21: B7 162

   Now, we need to pick 15 blocks, with at least 1 from each channel, and not exceeding channel maxes (A≤8, B≤7, C≤6).
   Greedy by rank: pick top ranks while respecting constraints.
   Start: must pick at least 1A, 1B, 1C. So we can think of forcing the minimum first, then picking the best remaining.
   But greedy from top overall might conflict with min constraints. Let's do it properly.

   Total blocks to pick: 15.
   Minimums: 1A, 1B, 1C → 3 blocks. Remaining 12 from the pool, but we can also add more to channels.

   If I just pick the absolute top 15 blocks from the 21, ignoring mins and maxes, then adjust:
   Top 15 by rank:
   C1, C2, B1, B2, B3, A1, A2, A3, A4, C3, C4, C5, C6, A5, A6.
   That's: A: A1-A4 + A5,A6 = 6 blocks. B: B1-B3 = 3 blocks. C: C1-C6 = 6 blocks. Sum = 15.
   Check mins: A has 6 ≥1, B has 3 ≥1, C has 6 ≥1. Maxes: A≤8 ok, B≤7 ok, C≤6 ok (exactly 6).
   This allocation is exactly A=6, B=3, C=6. And it's the top 15 blocks when considering all expected marginal gains, respecting that we can't pick more than available per channel, and the top 15 naturally respect mins and maxes because the forced mins are low enough and maxes high enough that the top 15 fill them optimally.

   Let's verify: If I tried to pick B4 instead of A6, B4 is rank 18, A6 is rank 15, so A6 is better. If I pick C something, C is already maxed at 6 in the top 15. If I reduce C to 5 and increase B to 4, I'd replace C6 (rank 13, 250) with B4 (rank 18, 162), net loss 88. So A=6, B=3, C=6 is optimal.

   Now, compute the required outputs.

   1. Optimal distribution: A=6 blocks, B=3 blocks, C=6 blocks.
   2. Per channel: number of blocks, expected listeners, gross margin, net profit.
      - For each channel, expected listeners = sum of marginal expected gains for allocated blocks.
      - Gross margin = total expected listeners * $4.
      - Net profit = gross margin - $15,000.

   Let's calculate per channel:
   Channel A: 6 blocks.
     Blocks 1-4: 450 each = 1800
     Blocks 5-6: 220 each = 440
     Total expected listeners A = 2240
     Gross margin A = 2240 * 4 = $8,960
   Channel B: 3 blocks.
     Expected marginal per block = 0.9 * 600 = 540 (for blocks 1-3)
     Total expected listeners B = 540 * 3 = 1620
     Gross margin B = 1620 * 4 = $6,480
   Channel C: 6 blocks.
     Blocks 1-2: 750 each = 1500
     Blocks 3-6: 250 each = 1000
     Total expected listeners C = 2500
     Gross margin C = 2500 * 4 = $10,000

   Total expected listeners = 2240 + 1620 + 2500 = 6360
   Total gross margin = 6360 * 4 = $25,440
   Net profit = 25,440 - 15,000 = $10,440

   3. Show overall total and worst-case scenario when B gives 50% result.
      Worst-case for B: 20% probability, B gives only 50% of announced result.
      Announced result for B with 3 blocks: 3 * 600 = 1800 listeners (without prob).
      But wait, the marginal gains are 600 each for blocks 1-3. So total announced listeners from B = 1800.
      With 50% result, actual listeners = 0.5 * 1800 = 900.
      However, the problem says: "Для канала B существует вероятность 20%, что он даст только 50% заявленного результата; в остальных 80% он даст полный результат."
      For the main calculation, we use mathematical expectation: 0.8 * full + 0.2 * 50% = 0.9 full.
      For worst-case scenario, we consider the case where B gives 50% result.
      So in worst case, B's expected listeners drop from 1620 to 900 (a loss of 720 listeners).
      But we need to show "отдельно худший сценарий, когда B даёт 50% результата."
      So worst-case gross margin: A and C remain as calculated (their results are deterministic? The problem only mentions uncertainty for B). So A: 2240 listeners, C: 2500 listeners. B: 900 listeners (50% of 1800). Total worst-case listeners = 2240 + 900 + 2500 = 5640.
      Gross margin worst = 5640 * 4 = $22,560.
      Net profit worst = 22,560 - 15,000 = $7,560.

      Alternatively, should I compute worst-case based on the announced blocks' total? Yes.

   4. Brief explanation why optimal: Greedy allocation by highest marginal expected listeners per block, respecting diminishing returns and channel caps, yields the top 15 blocks from the pooled marginal gains, which happens to be A=6, B=3, C=6. This maximizes total expected listeners, and since net profit = (listeners * 4) - 15000, it maximizes net profit.

   Now, format: "компактная Markdown-таблица, затем расчёт общего итога и вывод. Не более 350 слов."

   I need to produce a markdown table. Let's design it.

   Table columns: Channel, Blocks, Expected Listeners, Gross Margin ($), Net Profit ($)
   Rows: A, B, C, then maybe Totals and Worst-case separately.

   But the prompt says: "1. Найти распределение блоков... 2. Показать по каждому каналу: число блоков, ожидаемых слушателей, валовую маржу и чистую прибыль. 3. Показать общий итог и отдельно худший сценарий, когда B даёт 50% результата. 4. Кратко объяснить, почему распределение оптимально."

   So the table can have rows for A, B, C with those metrics, then below or above the total and worst-case. I'll put the per-channel data in a table, then total and worst-case below.

   Let's ensure calculations are double-checkered.

   Budget: $15,000, 15 blocks of $1,000. Spent exactly.
   Min 1 block each: satisfied.
   Maxes: A≤8, B≤7, C≤6: A=6 ok, B=3 ok, C=6 ok.

   Marginal gains re-verify:
   A: 1-4: 450, 5-8: 220. A has 6 blocks → 4*450 + 2*220 = 1800+440=2240. Correct.
   B: 1-3: 600, 4-7: 180. With 0.9 expectation: 3*540=1620. Correct.
   C: 1-2: 750, 3-6: 250. C has 6 blocks → 2*750 + 4*250 = 1500+1000=2500. Correct.

   Gross margin = listeners * 4:
   A: 2240*4=8960
   B: 1620*4=6480
   C: 2500*4=10000
   Total gross = 25440
   Net profit = 25440 - 15000 = 10440

   Worst-case B: 50% of announced result. Announced result for B with 3 blocks: 3*600=1800. 50% = 900.
   Wait, the problem says "вероятность 20%, что он даст только 50% заявленного результата". For worst-case scenario, we just take the 50% outcome, regardless of the 20% probability. So B listeners = 900.
   Total worst listeners = A(2240) + C(2500) + B(900) = 5640.
   Gross worst = 5640*4 = 22560.
   Net worst = 22560 - 15000 = 7560.

   Check if "заявленного результата" means the total expected from blocks, or per block. It says "даст только 50% заявленного результата", likely meaning the total output from that channel is halved. So 1800 * 0.5 = 900. Correct.

   Now, format. I'll create a markdown table:

   | Channel | Blocks | Expected Listeners | Gross Margin ($) | Net Profit ($) |
   |---------|--------|-------------------|------------------|----------------|
   | A       | 6      | 2,240             | 8,960            | -6,040         |
   | B       | 3      | 1,620             | 6,480            | -8,520         |
   | C       | 6      | 2,500             | 10,000           | -5,000         |
   | **Total** | **15** | **6,360**         | **25,440**       | **10,440**     |
   | **Worst-case (B at 50%)** | **15** | **5,640**         | **22,560**       | **7,560**      |

   Wait, net profit per channel individually doesn't make much sense because the budget is shared, but the prompt says "Показать по каждому каналу: число блоков, ожидаемых слушателей, валовую маржу и чистую прибыль." I could show per-channel gross margin and net profit if we attribute the fixed ad spend proportionally, or just show total net profit and per-channel contributions to listeners/margin. But it says "по каждому каналу: число блоков, ожидаемых слушателей, валовую маржу и чистую прибыль." I think it's fine to show per-channel expected listeners and gross margin, and then net profit total. Maybe show net profit as total, but I can show per-channel gross margin and note that net profit is total minus 15000. To be precise, I'll show per-channel listeners and gross margin, and then total net profit. The table can have per-channel gross margin, and net profit row is total. Or I can calculate per-channel net profit by allocating ad spend equally? No, the ad spend is $15k total, not per channel. The prompt says "Для каждого канала нужно выделить минимум один блок." and budget is total. So net profit is overall. I'll show per-channel listeners and gross margin, and total net profit. The table can have columns: Channel, Blocks, Expected Listeners, Gross Margin ($). Then below, Total expected listeners, Total gross margin, Net Profit ($). And worst-case separately.

   Let's re-read: "2. Показать по каждому каналу: число блоков, ожидаемых слушателей, валовую маржу и чистую прибыль." Maybe they want per-channel net profit calculated as (listeners * 4) - (proportional ad spend)? But ad spend isn't specified per channel; it's a total pool. Since blocks cost $1k each, and we allocate blocks, the ad spend per channel is blocks * $1k. So net profit per channel could be gross margin from that channel minus its ad spend. That makes sense! Because each block is $1k, so channel A ad spend = 6 * 1000 = $6k, B = $3k, C = $6k. Then net profit per channel = gross margin - ad spend. Total net profit = sum = 25440 - 15000 = 10440. This is likely what they want: "чистую прибыль" per channel after its own ad costs. Let's check: "Each new listener brings $4 expected gross margin before advertising expenses." So gross margin = listeners * 4. Net profit for a channel = gross margin - ad spend on that channel. Since ad spend is block count * 1000. This fits perfectly. I'll do that.

   So:
   Channel A: 6 blocks → ad spend $6,000. Expected listeners 2,240. Gross margin = 2,240 * 4 = $8,960. Net profit = 8,960 - 6,000 = $2,960.
   Channel B: 3 blocks → ad spend $3,000. Expected listeners 1,620. Gross margin = 1,620 * 4 = $6,480. Net profit = 6,480 - 3,000 = $3,480.
   Channel C: 6 blocks → ad spend $6,000. Expected listeners 2,500. Gross margin = 2,500 * 4 = $10,000. Net profit = 10,000 - 6,000 = $4,000.
   Total net profit = 2,960 + 3,480 + 4,000 = $10,440. Matches.

   Worst-case B at 50%: B's expected listeners drop to 900. Gross margin B = 900 * 4 = $3,600. Ad spend B = $3,000. Net profit B = 3,600 - 3,000 = $600. A and C remain same. Total net worst = A net 2,960 + C net 4,000 + B net 600 = $7,560. Matches earlier total net.

   This is much cleaner. I'll structure the table with these per-channel metrics.

   Table:
   | Channel | Blocks | Expected Listeners | Gross Margin ($) | Ad Spend ($) | Net Profit ($) |
   |---------|--------|-------------------|------------------|--------------|----------------|
   | A       | 6      | 2,240             | 8,960            | 6,000        | 2,960          |
   | B       | 3      | 1,620             | 6,480            | 3,000        | 3,480          |
   | C       | 6      | 2,500             | 10,000           | 6,000        | 4,000          |
   | **Total** | **15** | **6,360**         | **25,440**       | **15,000**   | **10,440**     |
   | **Worst-case (B at 50%)** | **15** | **5,640**         | **22,560**       | **15,000**   | **7,560**      |

   Check worst-case total listeners: A 2240 + C 2500 + B 900 = 5640. Gross: 5640*4=22560. Ad spend 15000. Net 7560. Correct.

   Now, the explanation: "Кратко объяснить, почему распределение оптимально." I'll add a short sentence after the table/output.

   Word count check: Need to stay ≤350 words. The table and brief calculations should be well under.

   Let's draft the response.

   First, verify all numbers one more time.

   Allocation: A=6, B=3, C=6. Sum=15.
   A blocks: 1-4: 450 each, 5-6: 220 each. Expected listeners = 4*450 + 2*220 = 1800+440=2240. Gross = 8960. Ad spend = 6000. Net = 2960.
   B blocks: 1-3. Announced 600 each, expected 540 each (0.9 factor). Listeners = 1620. Gross = 6480. Ad spend = 3000. Net = 3480.
   C blocks: 1-2: 750 each, 3-6: 250 each. Listeners = 2*750 + 4*250 = 1500+

> **Метрики:** 175.47 с; input=504 (cache hit=0, miss=0); output=8000; reasoning=5576; total=8504; free; cost=$0.000000; finish=length

### ZEN СРЕДНЯЯ: OpenCode Zen / mimo-v2.5-free
#### Оптимальное распределение: A = 6, B = 3, C = 6 блоков

##### Поиск оптимума

| Блок | Маржинальная выручка | Стоимость | Чистый эффект |
|------|---------------------|-----------|---------------|
| C1 | 750 × $4 = $3 000 | $1 000 | **+$2 000** |
| C2 | 750 × $4 = $3 000 | $1 000 | **+$2 000** |
| B1–B3 | 540 × $4 = $2 160 | $1 000 | **+$1 160** |
| A1–A4 | 450 × $4 = $1 800 | $1 000 | **+$800** |
| C3–C6 | 250 × $4 = $1 000 | $1 000 | **$0** |
| A5–A8 | 220 × $4 = $880 | $1 000 | −$120 |
| B4–B7 | 162 × $4 = $648 | $1 000 | −$352 |

> Набираем блоки по убыванию чистого эффекта: 2 (C) + 3 (B) + 4 (A) + 4 (C₃₋₆) + 2 (A₅₋₆) = **15** ✓

##### Результаты по каналам

| Канал | Блоки | Ожид. слушатели | Валовая маржа | Стоимость | Чистая прибыль |
|-------|-------|----------------|---------------|-----------|----------------|
| **A** | 6 | 4×450 + 2×220 = **2 240** | 2 240 × $4 = **$8 960** | $6 000 | **$2 960** |
| **B** | 3 | 3×600 = 1 800 ном.; ожид. = 0,8×1800 + 0,2×900 = **1 620** | 1 620 × $4 = **$6 480** | $3 000 | **$3 480** |
| **C** | 6 | 2×750 + 4×250 = **2 500** | 2 500 × $4 = **$10 000** | $6 000 | **$4 000** |
| **Итого** | **15** | **6 360** | **$25 440** | **$15 000** | **$10 440** |

##### Худший сценарий (B = 50%)

| | B слушатели | B маржа | B прибыль | **Общая чистая прибыль** |
|---|---|---|---|---|
| Ожидание | 1 620 | $6 480 | $3 480 | **$10 440** |
| Худший | 900 | $3 600 | $600 | **$7 560** |

##### Почему это оптимально

Все блоки с положительным чистым эффектом (**C1–C2**, **B1–B3**, **A1–A4**) обязательны. Оставшиеся 4 блока (C3–C6) имеют нулевой эффект — лучше их, чем A5–A8 (−$120) или B4–B7 (−$352). Финальные 2 блока идут в A₅₋₆ (минимальные потери −$120). Любое перераспределение снижает прибыль.

> **Метрики:** 59.59 с; input=541 (cache hit=0, miss=0); output=5031; reasoning=0; total=5572; free; cost=$0.000000; finish=stop

### ZEN СИЛЬНАЯ: OpenCode Zen / nemotron-3-ultra-free
**Оптимальное распределение (математическое ожидание)**

| Канал | Блоков | Ожид. слушателей | Вал. маржа | Числ. прибыль |
|-------|--------|------------------|------------|---------------|
| A     | 6      | 2 240            | $8 960     | $2 960        |
| B     | 3      | 1 620            | $6 480     | $3 480        |
| C     | 6      | 2 500            | $10 000    | $4 000        |
| **Итого** | **15** | **6 360**        | **$25 440**| **$10 440**   |

**Худший сценарий (B даёт 50 %)**

| Канал | Слушателей | Вал. маржа | Числ. прибыль |
|-------|------------|------------|---------------|
| A     | 2 240      | $8 960     | $2 960        |
| B     | 900        | $3 600     | $600          |
| C     | 2 500      | $10 000    | $4 000        |
| **Итого** | **5 640**  | **$22 560**| **$7 560**    |

**Почему оптимально:** Предельные ожидаемые слушатели на блок не возрастают внутри каждого канала. Жадное распределение 12 оставшихся блоков (после минимумов) к наивысшим текущим предельным значениям даёт последовательность: C1‑2 (750), B1‑3 (540), A1‑4 (450), C3‑6 (250), A5‑6 (220). Результат A=6, B=3, C=6 удовлетворяет всем ограничениям. Любая замена блока на более низкий предельный прирост снизит ожидаемую валовую маржу и чистую прибыль.

> **Метрики:** 127.41 с; input=504 (cache hit=0, miss=0); output=5035; reasoning=3155; total=5539; free; cost=$0.000000; finish=stop
