# AMR Pilot: User Adjudication Completed

Run: `run-20260724T125522Z`

Choose exactly one outcome for each gold-item dispute: `supported`, `omitted`, or `incorrect`.

## 1. BLIND-117260513219 / AMR-S012 / AMR-S012-G001

Source sentence: Even if you name Stephanie in your will, the court will review the appointment to ensure it is in the best interest of the children.

Gold statement: Naming Stephanie in the will is presented as a concessive condition.

Reviewer outcomes: R1=`omitted`, R2=`incorrect`

Candidate:

```text
(r / review-01
   :ARG0 (c / court)
   :ARG1 (a / appoint-01
            :ARG1 (p / person
                     :name (n / name
                              :op1 "Stephanie")))
   :condition (n2 / name-01
                  :ARG0 (y / you)
                  :ARG1 p
                  :location (w / will
                               :poss y))
   :purpose (e / ensure-01
                :ARG1 (i / interest-01
                           :domain a
                           :mod (b / best)
                           :ARG1 (c2 / child))))
```

User outcome: `[ ] supported` `[ ] omitted` `[x] incorrect`

## 2. BLIND-117260513219 / AMR-S012 / AMR-S012-G002

Source sentence: Even if you name Stephanie in your will, the court will review the appointment to ensure it is in the best interest of the children.

Gold statement: The court will review the appointment.

Reviewer outcomes: R1=`omitted`, R2=`supported`

Candidate:

```text
(r / review-01
   :ARG0 (c / court)
   :ARG1 (a / appoint-01
            :ARG1 (p / person
                     :name (n / name
                              :op1 "Stephanie")))
   :condition (n2 / name-01
                  :ARG0 (y / you)
                  :ARG1 p
                  :location (w / will
                               :poss y))
   :purpose (e / ensure-01
                :ARG1 (i / interest-01
                           :domain a
                           :mod (b / best)
                           :ARG1 (c2 / child))))
```

User outcome: `[x] supported` `[ ] omitted` `[ ] incorrect`

## 3. BLIND-237126303881 / AMR-S012 / AMR-S012-G002

Source sentence: Even if you name Stephanie in your will, the court will review the appointment to ensure it is in the best interest of the children.

Gold statement: The court will review the appointment.

Reviewer outcomes: R1=`omitted`, R2=`supported`

Candidate:

```text
(p / prevent-01
   :polarity -
   :ARG0 (n / name-01
            :ARG0 (y / you)
            :ARG1 (s / person
                     :name (sn / name
                               :op1 "Stephanie"))
            :location (w / will))
   :ARG1 (r / review-01
            :ARG0 (c / court)
            :ARG1 (a / appoint-01)
            :purpose (e / ensure-01
                      :ARG1 (h / have-condition-91
                               :ARG1 a
                               :ARG2 (i / interest
                                        :mod (b / best)
                                        :poss (ch / child))))))
```

User outcome: `[ ] supported` `[x] omitted` `[ ] incorrect`

## 4. BLIND-314258994197 / AMR-S004 / AMR-S004-G003

Source sentence: Well, I'll be leaving today and coming back on the 19th.

Gold statement: The speaker will return.

Reviewer outcomes: R1=`incorrect`, R2=`supported`

Candidate:

```text
(a / and
   :op1 (l / leave-01
            :ARG0 (s / person)
            :time (t / today))
   :op2 (r / return-01
            :ARG1 s
            :time (d / date-entity
                     :day 19)))
```

User outcome: `[x] supported` `[ ] omitted` `[ ] incorrect`

## 5. BLIND-336825660974 / AMR-S008 / AMR-S008-G002

Source sentence: It seems that the exact item you want to exchange for is currently not available in our inventory.

Gold statement: The affected object is the exact item the addressee wants as an exchange replacement.

Reviewer outcomes: R1=`omitted`, R2=`supported`

Candidate:

```text
(s / seem-01
   :ARG1 (a / available-02
            :polarity -
            :ARG1 (i / item
                     :mod (e / exact)
                     :ARG2-of (x / exchange-01
                                  :ARG0 (y / you)
                                  :ARG1-of (w / want-01
                                               :ARG0 y)))
            :time (n / now)
            :location (v / inventory
                         :poss (w2 / we))))
```

User outcome: `[x] supported` `[ ] omitted` `[ ] incorrect`

## 6. BLIND-497402352816 / AMR-S006 / AMR-S006-G002

Source sentence: By following these steps and adhering to the timeline, you should be able to finalize your will by the deadline of May 15, 2024.

Gold statement: The addressee is said to have an expected ability, not a guarantee.

Reviewer outcomes: R1=`incorrect`, R2=`supported`

Candidate:

```text
(e / enable-01
   :ARG0 (a / and
            :op1 (f / follow-01
                    :ARG0 (y / you)
                    :ARG1 (s / step))
            :op2 (a2 / adhere-01
                     :ARG0 y
                     :ARG1 (t / timeline)))
   :ARG1 (f2 / finalize-01
             :ARG0 y
             :ARG1 (w / will
                       :poss y)
             :time (d / date-entity
                      :year 2024
                      :month 5
                      :day 15))
   :mod (s2 / should))
```

User outcome: `[x] supported` `[ ] omitted` `[ ] incorrect`

## 7. BLIND-609528877878 / AMR-S012 / AMR-S012-G003

Source sentence: Even if you name Stephanie in your will, the court will review the appointment to ensure it is in the best interest of the children.

Gold statement: The object of the court's review is the appointment of Stephanie.

Reviewer outcomes: R1=`omitted`, R2=`supported`

Candidate:

```text
{"schema_version":"amr-pilot-atomic-knowledge-v1","items":[{"knowledge_id":"K001","statement":"Naming Stephanie in your will does not prevent the court from reviewing the appointment.","evidence_quote":"Even if you name Stephanie in your will, the court will review the appointment"},{"knowledge_id":"K002","statement":"The court will review the appointment.","evidence_quote":"the court will review the appointment"},{"knowledge_id":"K003","statement":"The purpose of the court's review of the appointment is to ensure that the appointment is in the best interest of the children.","evidence_quote":"to ensure it is in the best interest of the children"}],"representation_gaps":[]}
```

User outcome: `[ ] supported` `[x] omitted` `[ ] incorrect`
