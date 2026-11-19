# Superseded: Manuscript Revisions for Perceived Reliability and SUS

> **Do not apply the revisions below.** The user confirmed that Chapters 1-3 and the questionnaire are already approved and must remain unchanged. Acceptance Testing now follows the approved SUS-only analysis in [Acceptance_Testing.md](Acceptance_Testing.md). The earlier proposals below are retained as historical reference.

Use this guide to edit the thesis manually while keeping its existing formatting. It provides replacement text for the passages affected by including both perceived reliability and SUS in Acceptance Testing. The four reliability statements supplement the standard ten-item SUS and are analyzed separately.

Page numbers below refer to the [updated PDF](<BANANAVISION_ AN INTELLIGENT SYSTEM FOR BANANA RIPENESS DETECTION (1).pdf>) before these edits. The replacement passages describe the questionnaire that was administered; they do not establish that the additional reliability items were previously approved or validated. The source PDF and survey workbook have not been edited.

When copying, paste only the replacement paragraphs into the editable thesis using its existing paragraph style or the editor's **Keep Text Only** option. Keep the current headings, numbering, indentation, line spacing, and caption styles. Page references will move after insertion.

For objective 5 and limitation 5, keep the existing list number. If the editor supplies numbering automatically, paste only the text after the displayed "5." below.

| Section | Printed Page | PDF Viewer Page | Manual Edit |
| --- | --- | --- | --- |
| Objectives of the Study | 6 | 18 | Replace objective 5 |
| Limitations | 10 | 22 | Replace limitation 5 |
| Research Methodology | 66-67 | 78-79 | Replace the pilot-evaluation sentences identified below |
| Acceptance Testing | 186 | 198 | Insert the separate acceptance-testing draft |
| Abstract | ii | 2 | Add the brief user-evaluation findings below |
| Conclusion | 209 | 221 | Add one paragraph on the acceptance results |
| Recommendations | 210-211 | 222-223 | Add one follow-up evaluation recommendation |
| List of Tables | xi-xii | 11-12 | Add the final acceptance-table captions and page numbers |

## 1. Objectives of the Study: Replace Objective 5

**Location:** Printed page 6 / PDF viewer page 18, immediately before **Scope and Limitations of the Study**.

**Find:** The numbered item beginning "Evaluate the system's classification performance" and ending "among selected medium and large enterprise operators."

**Replacement text:**

5. Evaluate the system's classification performance in terms of accuracy, precision, and recall benchmarked against a baseline color-histogram classifier, assess the predictive performance of the RFR spoilage model in terms of Mean Absolute Error (MAE), and evaluate user-perceived reliability and usability among selected enterprise pilot participants assigned Administrator or Operator roles, using four supplementary reliability statements and the ten-item System Usability Scale (SUS).

The model-performance portion of this objective is retained. The amendment identifies the additional perception measure and both assigned evaluation roles.

## 2. Limitations: Replace Item 5

**Location:** Printed page 10 / PDF viewer page 22, immediately before **Significance of the Study**.

**Find:** The numbered item beginning "Usability testing is limited to a supervised pilot test with 3 to 5 selected operators" and ending "rather than a widespread public deployment."

**Replacement text:**

5. Acceptance testing is limited to a supervised pilot evaluation designed around batch scanning and dashboard interpretation. Completed questionnaires were obtained from five participants at one wholesale banana distribution enterprise, with two assigned Administrator roles and three assigned Operator roles. The questionnaire included four supplementary, study-specific statements on perceived reliability and the ten standard System Usability Scale (SUS) statements. The reliability responses describe perceptions of faultlessness, availability, fault tolerance, and recoverability, while SUS provides a separate composite usability score. These findings are limited to the participating group and do not establish broad enterprise acceptance or objective measures of uptime, recovery time, or performance during controlled interruptions. The numerical export does not preserve the original response-scale labels, so agreement-based interpretations remain subject to confirmation against the original questionnaire.

This replacement reports the five actual respondents without implying that all were assigned Operator roles or that several enterprises participated.

## 3. Research Methodology: Replace the Pilot-Evaluation Passage

**Location:** Printed pages 66-67 / PDF viewer pages 78-79, within the methodology narrative after the discussion of continuous validation and hardware-in-the-loop testing.

**Select only these four sentences, which cross the page boundary:**

> To mitigate the risks associated with large-scale deployment, a supervised pilot test rollout has been designed. Multi-camera IoT edge devices will be deployed to 3 to 5 selected enterprise operators to scan real fruit batches. Vendor interaction with the dashboard results will then be evaluated using a standard System Usability Scale (SUS) questionnaire. This pilot establishes a direct operational link between the physical edge units and the Wi-Fi-based dashboard.

Stop the selection before the next sentence, which begins **"Supported by established CI/CD pipelines for edge AI"**. Keep the surrounding model-validation and development-process text.

**Replacement text:**

The user evaluation was designed as a supervised pilot centered on batch scanning and interpretation of kiosk and dashboard results. Completed acceptance questionnaires were obtained from five evaluators at one wholesale banana distribution enterprise. Two participants were assigned Administrator roles for web dashboard and management activities, and three were assigned Operator roles for kiosk terminal and batch-scanning activities.

The administered questionnaire included respondent-profile questions, four supplementary, study-specific statements on perceived reliability, the ten standard System Usability Scale (SUS) statements, and optional comments. The reliability statements addressed faultlessness, availability, fault tolerance, and recoverability, with one statement for each dimension. They assessed users' perceptions and were analyzed separately from SUS. The four additional statements were not treated as a validated technical reliability instrument or included in the SUS score.

Reliability responses were summarized using weighted means and sample standard deviations. An overall descriptive reliability rating was calculated by averaging each respondent's four reliability responses and then averaging the five respondent-level values. Its standard deviation was calculated across those five respondent-level averages. SUS scores were calculated using the standard procedure: subtract 1 from each odd-numbered response, subtract each even-numbered response from 5, add the ten contributions, and multiply the sum by 2.5 (Brooke, 1996). The mean and sample standard deviation of the five SUS scores were then calculated. Optional comments were summarized descriptively to provide context for the quantitative findings.

For the reported analysis, numerical responses were interpreted using conventional five-point agreement coding, from 1 for Strongly Disagree to 5 for Strongly Agree. The reliability reporting bands were 1.00-1.80 for Strongly Disagree, 1.81-2.60 for Disagree, 2.61-3.40 for Neutral, 3.41-4.20 for Agree, and 4.21-5.00 for Strongly Agree. These are descriptive reporting conventions rather than technical pass/fail criteria. The export does not retain the form's written response anchors, so verbal interpretations require confirmation against the original instructions. The reliability and SUS results were reported separately, with no combined acceptance score.

**Citation placement:** Brooke (1996) supports the SUS scoring procedure. The reliability summaries, reporting bands, and comment analysis are this report's stated analysis conventions; they are not presented as requirements of SUS.

## 4. Acceptance Testing: Insert the Completed Section

**Location:** Printed page 186 / PDF viewer page 198. This page currently contains only the **Acceptance Testing** heading.

Use [Acceptance_Testing.md](Acceptance_Testing.md). Keep the existing heading and insert the body text from its introductory paragraph through **Overall Conclusion of Acceptance Testing**. Its **Sources and Calculation Notes** section is an editing reference, rather than part of the manuscript narrative.

Include both result groups:

- **User-perceived reliability:** The four supplementary statements, their means and SDs, and the corresponding discussion and conclusion.
- **SUS:** The ten standard statements, separately calculated respondent SUS scores, and the corresponding discussion and conclusion.

Retain the evaluator profile and qualitative feedback. Use the thesis's existing table and caption formatting when recreating the three tables.

## 5. Abstract: Add the User-Evaluation Findings

**Location:** Printed page ii / PDF viewer page 2.

**Insert after:** The sentence ending "Root Mean Squared Error (RMSE) of 0.9822 days, and R² of 0.9552."

**Insert before:** The existing sentence beginning "BananaVision integrates automated ripeness detection".

**Text to add within the existing abstract paragraph:**

A pilot questionnaire completed by five evaluators from one wholesale banana distributor produced an overall perceived-reliability mean of 4.40 out of 5 and a mean SUS score of 49.00 out of 100 under standard scoring. Agreement with both positive and negative SUS statements requires clarification of response interpretation before a final usability conclusion.

## 6. Conclusion: Add One Paragraph About Acceptance Testing

**Location:** Printed page 209 / PDF viewer page 221.

**Insert before:** The paragraph beginning "BananaVision demonstrates the potential of IoT-based monitoring to support inventory rotation".

**Paragraph to add:**

The pilot acceptance evaluation provided initial user feedback through four supplementary perceived-reliability statements and the ten-item System Usability Scale. Five evaluators from one wholesale banana distribution enterprise produced an overall perceived-reliability mean of 4.40 out of 5 and a mean SUS score of 49.00 out of 100 under standard scoring. Although the reliability ratings were favorable under conventional agreement coding, the SUS responses showed agreement with both positive and negative statements. The findings therefore support a positive preliminary perception of reliability while identifying unresolved usability concerns. Verification of the original response instructions and further user evaluation are needed before drawing a broader acceptance conclusion.

## 7. Recommendations: Add One Follow-Up Evaluation Item

**Location:** The existing recommendations list on printed pages 210-211 / PDF viewer pages 222-223. Add this item using the same bullet style as the other recommendations.

**Bullet text to add:**

- Expand the pilot acceptance evaluation to include more participants from additional enterprises and both assigned user roles. Verify the original questionnaire's response anchors and instructions, clarify the conflicting positive and negative SUS responses, and preserve the original records when conducting any new evaluation. Report supplementary perceived-reliability ratings separately from SUS, and complement them with documented task-completion and operational reliability measurements.

## 8. List of Tables and Reference Entry

The last numbered table in the manuscript body before testing is **Table 45: BananaVision List of Module**. Continue with these captions, as used in the acceptance draft:

- **Table 46: User-Perceived Reliability Dimension Table**
- **Table 47: System Usability Scale Item Responses**
- **Table 48: Respondent-Level System Usability Scale Scores**

Update the List of Tables using the actual page numbers after insertion. Update the Acceptance Testing entry in the Table of Contents if its position or length changes. Keep the existing list formatting.

If the bibliography does not already contain Brooke's SUS reference, add it using the thesis's existing reference style:

Brooke, J. (1996). SUS: A "quick and dirty" usability scale. In P. W. Jordan, B. Thomas, B. A. Weerdmeester, & I. L. McClelland (Eds.), *Usability Evaluation in Industry* (pp. 189-194). Taylor & Francis.

[Original SUS scoring reference](https://hci-studies.org/methods-and-measures/downloads/SUS_Brooke1996.pdf)

## Editing Notes

Both measures can appear in Acceptance Testing. The four additional reliability statements remain separate from the standard ten-item SUS. Their inclusion does not establish instrument validation or prior approval, and their ratings are perceptions rather than controlled technical measurements.

The proposed text uses the previously verified survey results without altering responses: overall perceived reliability **4.40/5**, SUS mean **49.00/100**, and five respondents assigned two Administrator and three Operator roles. Do not combine the reliability ratings with the SUS calculation. The original form's anchors still need confirmation before the agreement-based interpretations are finalized.
