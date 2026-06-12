-- =============================================================================
-- IL Explainability App — Spark SQL
-- Protection Lapse Propensity (under-55, excl. UL)
-- Compatible with: Apache Spark / DataRobot AI Catalog SQL notebook
--
-- USAGE
--   1. Upload the scoring Excel file to the AI Catalog as a dataset.
--      DataRobot will register it as a Spark table — use the table name
--      provided in the Catalog (referred to below as <scoring_source>).
--   2. Run Section 1 once to create the lookup table.
--   3. Run Sections 2–4 to create the three derived views.
--   4. Use the views in Power BI or any downstream SQL consumer.
--
-- TABLES / VIEWS PRODUCED
--   il_feature_group_mapping   permanent table  feature → group lookup (editable)
--   vw_scored_population       view             source dataset cleaned + typed
--   vw_explanation_long        view             unpivoted SHAP slots with group labels
--   vw_group_shap_summary      view             group-level SHAP aggregation (full population)
--
-- NOTE ON COLUMN NAMES
--   Spark backtick-quotes column names with spaces or special characters.
--   The source dataset contains: `Benefit Combos Detailed`, `20-quantile`,
--   `Status_Cd at 26/05/2026`, `Status_Desc at 26/05/2026`.
--   These are quoted throughout.
-- =============================================================================


-- =============================================================================
-- SECTION 0 — configuration
-- Replace <scoring_source> with the Catalog table name of the uploaded dataset.
-- =============================================================================

-- SET source_table = '<scoring_source>';   -- uncomment and set if your dialect supports SET


-- =============================================================================
-- SECTION 1 — feature group mapping (permanent lookup table)
-- Edit group assignments here; re-run this section after any change.
-- Unmapped feature names fall through to 'Other' in the views below.
-- =============================================================================

CREATE TABLE IF NOT EXISTS il_feature_group_mapping (
    feature_name   STRING,
    feature_group  STRING
);

-- Truncate and reload so re-runs are idempotent
TRUNCATE TABLE il_feature_group_mapping;

INSERT INTO il_feature_group_mapping VALUES
-- Policy & Product
('Product_Desc',                    'Policy & Product'),
('Cover_Shrt_Nm',                   'Policy & Product'),
('Benefit Combos Detailed',         'Policy & Product'),
('AP_Amt',                          'Policy & Product'),
('Term',                            'Policy & Product'),
('Commencement_Date',               'Policy & Product'),
('Maturity_Date',                   'Policy & Product'),
('TTG_v2',                          'Policy & Product'),
('IndexationDesc',                  'Policy & Product'),
('CommencementYear',                'Policy & Product'),
('Duration',                        'Policy & Product'),
-- date-part features DataRobot extracts automatically
('Commencement_Date (Month)',        'Policy & Product'),
('Commencement_Date (Day of Week)',  'Policy & Product'),
('Commencement_Date (Day of Month)', 'Policy & Product'),
('Maturity_Date (Year)',             'Policy & Product'),
('Maturity_Date (Month)',            'Policy & Product'),
('Maturity_Date (Day of Week)',      'Policy & Product'),
('Maturity_Date (Day of Month)',     'Policy & Product'),

-- Policy Portfolio
('ProtPolsIF_Life1',                'Policy Portfolio'),
('ProtPolsIF_Life2',                'Policy Portfolio'),
('MortgPolsIF_Life1',               'Policy Portfolio'),
('MortgPolsIF_Life2',               'Policy Portfolio'),
('WOLPolsIF_Life1',                 'Policy Portfolio'),
('WOLPolsIF_Life2',                 'Policy Portfolio'),
('ProtPolsOOF_Last2yrs_Life1',      'Policy Portfolio'),
('ProtPolsOOF_Last2yrs_Life2',      'Policy Portfolio'),
('Life_Sum_Assured_Life1_Amt',       'Policy Portfolio'),
('Life_Sum_Assured_Life2_Amt',       'Policy Portfolio'),
('Sic_Sum_Assured_Life1_Amt',        'Policy Portfolio'),
('Sic_Sum_Assured_Life2_Amt',        'Policy Portfolio'),

-- Agent / Adviser
('Sl_Level3_Shortname',             'Agent / Adviser'),
('Sl_Level6_Shortname',             'Agent / Adviser'),
('Servicing_Agent_Cd',              'Agent / Adviser'),
('AuthorisedAdvisor',               'Agent / Adviser'),
('Source_Of_Business',              'Agent / Adviser'),
('Pols_IF_PerAgent',                'Agent / Adviser'),
('CommissionScaleCode',             'Agent / Adviser'),
('AgentLocation',                   'Agent / Adviser'),

-- Sociodemographic
('Age_life1',                       'Sociodemographic'),
('Age_life2',                       'Sociodemographic'),
('Gender',                          'Sociodemographic'),
('SmokerStatus',                    'Sociodemographic'),
('JobTitle_L1',                     'Sociodemographic'),
('FamilyStatusName_L1',             'Sociodemographic'),
('EmploymentStatus_L1',             'Sociodemographic'),
('Age_At_Review_L1',                'Sociodemographic'),
('Age_At_Review_L2',                'Sociodemographic'),

-- Financial Profile
('NetIncomeAmount_L1',              'Financial Profile'),
('SalaryAmount_L1',                 'Financial Profile'),
('TotalIncome_L1',                  'Financial Profile'),
('HouseholdDisposableIncomeMonthly_L1', 'Financial Profile'),
('FamilyHomeOutstandingBalance_L1', 'Financial Profile'),
('TotalLoansOutstandingBalance_L1', 'Financial Profile'),

-- Expenditure (kept separate from Financial Profile for group granularity)
('FoodMonthlyAmount_L1',            'Expenditure'),
('OtherExpensesMonthlyAmount_L1',   'Expenditure'),

-- Engagement & Reviews
('MonthsSinceReview',               'Engagement & Reviews'),
('OnlineServiesLogins_Last12Months_Life1', 'Engagement & Reviews'),
('ReviewCreatedOn_L1 (Month)',      'Engagement & Reviews'),
('ReviewCreatedOn_L1 (Day of Month)', 'Engagement & Reviews'),
('ReviewCreatedOn_L1 (Hour of Day)', 'Engagement & Reviews'),

-- Persona
('PersonaDesc_1',                   'Persona'),
('PersonaDesc_2',                   'Persona');


-- =============================================================================
-- SECTION 2 — vw_scored_population
-- One row per policy. Cleans types; renames awkward columns.
-- Source: the AI Catalog dataset uploaded from the scoring Excel file.
-- Replace <scoring_source> with the actual Catalog table name.
-- =============================================================================

CREATE OR REPLACE VIEW vw_scored_population AS
SELECT
    Policy_Number,

    -- prediction outputs
    CAST(Lapse_ind_1_PREDICTION AS DOUBLE)  AS lapse_score,
    CAST(Lapse_ind_0_PREDICTION AS DOUBLE)  AS lapse_score_complement,
    Lapse_ind                               AS actual_outcome,   -- 'Y'/'N'/NULL
    CAST(Precentile AS DOUBLE)              AS score_percentile,
    CAST(Decile     AS INT)                 AS score_decile,
    CAST(`20-quantile` AS INT)              AS score_quantile_20,

    -- explanation slots (kept wide for CohortFilter "Top Driver" slicer)
    EXPLANATION_1_FEATURE_NAME,
    CAST(EXPLANATION_1_STRENGTH AS DOUBLE)  AS EXPLANATION_1_STRENGTH,
    TRIM(CAST(EXPLANATION_1_ACTUAL_VALUE AS STRING)) AS EXPLANATION_1_ACTUAL_VALUE,
    EXPLANATION_1_QUALITATIVE_STRENGTH,

    EXPLANATION_2_FEATURE_NAME,
    CAST(EXPLANATION_2_STRENGTH AS DOUBLE)  AS EXPLANATION_2_STRENGTH,
    TRIM(CAST(EXPLANATION_2_ACTUAL_VALUE AS STRING)) AS EXPLANATION_2_ACTUAL_VALUE,
    EXPLANATION_2_QUALITATIVE_STRENGTH,

    EXPLANATION_3_FEATURE_NAME,
    CAST(EXPLANATION_3_STRENGTH AS DOUBLE)  AS EXPLANATION_3_STRENGTH,
    TRIM(CAST(EXPLANATION_3_ACTUAL_VALUE AS STRING)) AS EXPLANATION_3_ACTUAL_VALUE,
    EXPLANATION_3_QUALITATIVE_STRENGTH,

    EXPLANATION_4_FEATURE_NAME,
    CAST(EXPLANATION_4_STRENGTH AS DOUBLE)  AS EXPLANATION_4_STRENGTH,
    TRIM(CAST(EXPLANATION_4_ACTUAL_VALUE AS STRING)) AS EXPLANATION_4_ACTUAL_VALUE,
    EXPLANATION_4_QUALITATIVE_STRENGTH,

    -- source features — Agent / Adviser
    Sl_Level3_Shortname,
    Sl_Level6_Shortname,
    AuthorisedAdvisor,
    Servicing_Agent_Cd,
    Source_Of_Business,
    CAST(Pols_IF_PerAgent AS BIGINT)        AS Pols_IF_PerAgent,
    CAST(CommissionScaleCode AS BIGINT)     AS CommissionScaleCode,
    AgentLocation,

    -- source features — Policy & Product
    CAST(Duration AS BIGINT)                AS Duration,
    CAST(Life_Sum_Assured_Life1_Amt AS BIGINT) AS Life_Sum_Assured_Life1_Amt,
    CAST(Sic_Sum_Assured_Life1_Amt AS BIGINT)  AS Sic_Sum_Assured_Life1_Amt,
    CAST(Life_Sum_Assured_Life2_Amt AS BIGINT) AS Life_Sum_Assured_Life2_Amt,
    CAST(Sic_Sum_Assured_Life2_Amt AS BIGINT)  AS Sic_Sum_Assured_Life2_Amt,
    IndexationDesc,
    BillFrequencyDesc,
    CAST(AP_Amt AS DOUBLE)                  AS AP_Amt,
    AnnualPremium_Band,
    CAST(CommencementYear AS INT)           AS CommencementYear,
    IfConvertedPolicy,
    ConversionOption,
    Product_SubCategory,
    TRIM(Product_Desc)                      AS Product_Desc,
    Cover_Shrt_Nm,
    CAST(Commencement_Date AS DATE)         AS Commencement_Date,
    CAST(Maturity_Date AS DATE)             AS Maturity_Date,
    CAST(Term AS INT)                       AS Term,
    CAST(TTG_v2 AS INT)                     AS TTG_v2,
    TRIM(`Benefit Combos Detailed`)         AS Benefit_Combos_Detailed,

    -- source features — Sociodemographic
    CAST(Age_life1 AS INT)                  AS Age_life1,
    CAST(Age_life2 AS INT)                  AS Age_life2,
    Gender,
    SmokerStatus,

    -- source features — Policy Portfolio
    CAST(OnlineServiesLogins_Last12Months_Life1 AS BIGINT) AS OnlineServiesLogins_Last12Months_Life1,
    CAST(OnlineServiesLogins_Last12Months_Life2 AS BIGINT) AS OnlineServiesLogins_Last12Months_Life2,
    CAST(ProtPolsIF_Life1  AS BIGINT)       AS ProtPolsIF_Life1,
    CAST(MortgPolsIF_Life1 AS BIGINT)       AS MortgPolsIF_Life1,
    CAST(OnePlanPolsIF_Life1 AS BIGINT)     AS OnePlanPolsIF_Life1,
    CAST(WOLPolsIF_Life1   AS BIGINT)       AS WOLPolsIF_Life1,
    CAST(UlProtPolsIF_Life1 AS BIGINT)      AS UlProtPolsIF_Life1,
    CAST(ProtPolsIF_Life2  AS BIGINT)       AS ProtPolsIF_Life2,
    CAST(MortgPolsIF_Life2 AS BIGINT)       AS MortgPolsIF_Life2,
    CAST(OnePlanPolsIF_Life2 AS BIGINT)     AS OnePlanPolsIF_Life2,
    CAST(WOLPolsIF_Life2   AS BIGINT)       AS WOLPolsIF_Life2,
    CAST(UlProtPolsIF_Life2 AS BIGINT)      AS UlProtPolsIF_Life2,
    CAST(ProtPolsOOF_Last2yrs_Life1  AS BIGINT) AS ProtPolsOOF_Last2yrs_Life1,
    CAST(MortgPolsOOF_Last2yrs_Life1 AS BIGINT) AS MortgPolsOOF_Last2yrs_Life1,
    CAST(OnePlanPolsOOF_Last2yrs_Life1 AS BIGINT) AS OnePlanPolsOOF_Last2yrs_Life1,
    CAST(WOLPolsOOF_Last2yrs_Life1   AS BIGINT) AS WOLPolsOOF_Last2yrs_Life1,
    CAST(UlProtPolsOOF_Last2yrs_Life1 AS BIGINT) AS UlProtPolsOOF_Last2yrs_Life1,
    CAST(ProtPolsOOF_Last2yrs_Life2  AS BIGINT) AS ProtPolsOOF_Last2yrs_Life2,
    CAST(MortgPolsOOF_Last2yrs_Life2 AS BIGINT) AS MortgPolsOOF_Last2yrs_Life2,
    CAST(OnePlanPolsOOF_Last2yrs_Life2 AS BIGINT) AS OnePlanPolsOOF_Last2yrs_Life2,
    CAST(WOLPolsOOF_Last2yrsF_Life2  AS BIGINT) AS WOLPolsOOF_Last2yrs_Life2,
    CAST(UlProtPolsOOF_Last2yrs_Life2 AS BIGINT) AS UlProtPolsOOF_Last2yrs_Life2,

    -- source features — Engagement & Reviews (L1)
    CAST(ReviewCreatedOn_L1 AS TIMESTAMP)   AS ReviewCreatedOn_L1,
    ReviewCompleted_L1,
    ReviewType_L1,
    CAST(DiscussedDeathProtection_L1   AS TINYINT) AS DiscussedDeathProtection_L1,
    CAST(DiscussedIllnessProtection_L1 AS TINYINT) AS DiscussedIllnessProtection_L1,
    CAST(DiscussedInvestments_L1       AS TINYINT) AS DiscussedInvestments_L1,
    CAST(DiscussedMortgages_L1         AS TINYINT) AS DiscussedMortgages_L1,
    CAST(DiscussedSavings_L1           AS TINYINT) AS DiscussedSavings_L1,
    CAST(MonthsSinceReview AS INT)      AS MonthsSinceReview,

    -- source features — Engagement & Reviews (L2)
    CAST(ReviewCreatedOn_L2 AS TIMESTAMP)   AS ReviewCreatedOn_L2,
    ReviewCompleted_L2,
    ReviewType_L2,

    -- source features — Sociodemographic (L1)
    JobTitle_L1,
    FamilyStatusName_L1,
    EmploymentStatus_L1,
    CAST(RetirementAge_L1           AS INT) AS RetirementAge_L1,
    CAST(Age_At_Review_L1           AS INT) AS Age_At_Review_L1,
    Providedfordependant_L1,
    CAST(NumberofDependents_L1      AS INT) AS NumberofDependents_L1,
    CAST(NumberofChildDEPENDENTS_L1 AS INT) AS NumberofChildDEPENDENTS_L1,
    CAST(AgeYoungestChild_L1        AS INT) AS AgeYoungestChild_L1,

    -- source features — Financial Profile (L1)
    CAST(SalaryAmount_L1            AS BIGINT) AS SalaryAmount_L1,
    CAST(NetIncomeAmount_L1         AS BIGINT) AS NetIncomeAmount_L1,
    CAST(OtherIncome_L1             AS BIGINT) AS OtherIncome_L1,
    CAST(TotalIncome_L1             AS BIGINT) AS TotalIncome_L1,
    CAST(HouseholdDisposableIncomeMonthly_L1 AS DOUBLE) AS HouseholdDisposableIncomeMonthly_L1,
    CAST(FamilyHomeOutstandingBalance_L1    AS BIGINT) AS FamilyHomeOutstandingBalance_L1,
    CAST(TotalLoansOutstandingBalance_L1    AS BIGINT) AS TotalLoansOutstandingBalance_L1,
    CAST(AssetsCurrentValue_L1      AS DOUBLE) AS AssetsCurrentValue_L1,

    -- source features — Expenditure (L1)
    CAST(FoodMonthlyAmount_L1           AS BIGINT) AS FoodMonthlyAmount_L1,
    CAST(MotorMonthlyAmount_L1          AS BIGINT) AS MotorMonthlyAmount_L1,
    CAST(OtherExpensesMonthlyAmount_L1  AS BIGINT) AS OtherExpensesMonthlyAmount_L1,
    CAST(ChildCareMonthlyAmount_L1      AS BIGINT) AS ChildCareMonthlyAmount_L1,
    CAST(HolidyMonthlyAmount_L1         AS BIGINT) AS HolidyMonthlyAmount_L1,

    -- Persona
    PersonaDesc_1,
    PersonaDesc_2

FROM <scoring_source>   -- ← replace with AI Catalog table name
;


-- =============================================================================
-- SECTION 3 — vw_explanation_long
-- Unpivots 4 wide explanation slots into one row per explanation.
-- Joins to il_feature_group_mapping to assign group labels.
-- Features not in the mapping table → 'Other'.
--
-- Output columns:
--   Policy_Number, explanation_rank (1–4), feature_name,
--   shap_strength, actual_value, qualitative_strength, feature_group
-- =============================================================================

CREATE OR REPLACE VIEW vw_explanation_long AS
WITH unpivoted AS (

    SELECT Policy_Number, 1 AS explanation_rank,
           EXPLANATION_1_FEATURE_NAME          AS feature_name,
           EXPLANATION_1_STRENGTH              AS shap_strength,
           EXPLANATION_1_ACTUAL_VALUE          AS actual_value,
           EXPLANATION_1_QUALITATIVE_STRENGTH  AS qualitative_strength
    FROM vw_scored_population
    WHERE EXPLANATION_1_FEATURE_NAME IS NOT NULL

    UNION ALL

    SELECT Policy_Number, 2,
           EXPLANATION_2_FEATURE_NAME,
           EXPLANATION_2_STRENGTH,
           EXPLANATION_2_ACTUAL_VALUE,
           EXPLANATION_2_QUALITATIVE_STRENGTH
    FROM vw_scored_population
    WHERE EXPLANATION_2_FEATURE_NAME IS NOT NULL

    UNION ALL

    SELECT Policy_Number, 3,
           EXPLANATION_3_FEATURE_NAME,
           EXPLANATION_3_STRENGTH,
           EXPLANATION_3_ACTUAL_VALUE,
           EXPLANATION_3_QUALITATIVE_STRENGTH
    FROM vw_scored_population
    WHERE EXPLANATION_3_FEATURE_NAME IS NOT NULL

    UNION ALL

    SELECT Policy_Number, 4,
           EXPLANATION_4_FEATURE_NAME,
           EXPLANATION_4_STRENGTH,
           EXPLANATION_4_ACTUAL_VALUE,
           EXPLANATION_4_QUALITATIVE_STRENGTH
    FROM vw_scored_population
    WHERE EXPLANATION_4_FEATURE_NAME IS NOT NULL
)

SELECT
    u.Policy_Number,
    u.explanation_rank,
    u.feature_name,
    u.shap_strength,
    u.actual_value,
    u.qualitative_strength,
    COALESCE(g.feature_group, 'Other')  AS feature_group
FROM unpivoted u
LEFT JOIN il_feature_group_mapping g
       ON u.feature_name = g.feature_name
;


-- =============================================================================
-- SECTION 4 — vw_group_shap_summary
-- Group-level SHAP aggregation over the FULL scored population.
-- For cohort-filtered aggregations, apply WHERE/JOIN in the consuming query
-- or Power BI DAX measure — do not pre-filter here.
--
-- Output columns:
--   feature_group, avg_shap, n_rows_with_coverage, coverage_pct,
--   n_total_policies
-- =============================================================================

CREATE OR REPLACE VIEW vw_group_shap_summary AS
WITH policy_count AS (
    SELECT COUNT(DISTINCT Policy_Number) AS n_total
    FROM vw_scored_population
)

SELECT
    el.feature_group,
    ROUND(AVG(el.shap_strength), 5)              AS avg_shap,
    COUNT(DISTINCT el.Policy_Number)             AS n_rows_with_coverage,
    ROUND(
        COUNT(DISTINCT el.Policy_Number) * 100.0
        / pc.n_total,
    1)                                           AS coverage_pct,
    pc.n_total                                   AS n_total_policies
FROM vw_explanation_long el
CROSS JOIN policy_count pc
GROUP BY el.feature_group, pc.n_total
ORDER BY ABS(AVG(el.shap_strength)) DESC
;


-- =============================================================================
-- SECTION 5 — cohort-scoped queries (run ad-hoc or parameterise in Power BI)
-- These are not materialised views — run them directly against the views above.
-- =============================================================================

-- 5.1 Group SHAP for a filtered cohort (example: Decile = 1, SmokerStatus = 'Smoker')
-- Replace the WHERE clause with any combination of scored_population columns.

SELECT
    el.feature_group,
    ROUND(AVG(el.shap_strength), 5)              AS avg_shap,
    COUNT(DISTINCT el.Policy_Number)             AS n_rows_with_coverage,
    ROUND(
        COUNT(DISTINCT el.Policy_Number) * 100.0
        / COUNT(DISTINCT sp.Policy_Number),
    1)                                           AS coverage_pct
FROM vw_scored_population sp
JOIN vw_explanation_long el ON sp.Policy_Number = el.Policy_Number
WHERE sp.score_decile = 1
  AND sp.SmokerStatus = 'Smoker'
  -- AND sp.Product_Desc LIKE '%Income%'
  -- AND sp.Age_life1 BETWEEN 30 AND 45
GROUP BY el.feature_group
ORDER BY ABS(AVG(el.shap_strength)) DESC
;


-- 5.2 Feature drill-down within a group for a filtered cohort

SELECT
    el.feature_name,
    ROUND(AVG(el.shap_strength), 5)              AS avg_shap,
    COUNT(DISTINCT el.Policy_Number)             AS n_rows
FROM vw_scored_population sp
JOIN vw_explanation_long el ON sp.Policy_Number = el.Policy_Number
WHERE el.feature_group = 'Agent / Adviser'
  AND sp.score_decile = 1
GROUP BY el.feature_name
ORDER BY ABS(AVG(el.shap_strength)) DESC
LIMIT 5
;


-- 5.3 Waterfall data for a single policy

SELECT
    el.explanation_rank,
    el.feature_name,
    el.shap_strength,
    el.actual_value,
    el.qualitative_strength,
    el.feature_group,
    sp.lapse_score
FROM vw_explanation_long el
JOIN vw_scored_population sp ON el.Policy_Number = sp.Policy_Number
WHERE el.Policy_Number = 'S1'   -- ← replace with target policy
ORDER BY ABS(el.shap_strength) DESC
;


-- 5.4 Cohort profile stats (score distribution summary)

SELECT
    COUNT(*)                                     AS n_rows,
    ROUND(AVG(lapse_score), 4)                   AS mean_score,
    ROUND(PERCENTILE(lapse_score, 0.5), 4)       AS median_score,
    ROUND(PERCENTILE(lapse_score, 0.9), 4)       AS p90_score,
    SUM(CASE WHEN actual_outcome = 'Y' THEN 1 ELSE 0 END)
        / COUNT(*)                               AS observed_lapse_rate
FROM vw_scored_population
WHERE score_decile = 1
  AND SmokerStatus = 'Smoker'
;


-- 5.5 Score histogram (20 equal-width bins across 0–1)
-- bin number = FLOOR(lapse_score * 20), capped at 19 so score=1.0 doesn't create bin 20

SELECT
    FLOOR(lapse_score * 20) / 20                 AS bin_start,
    FLOOR(lapse_score * 20) / 20 + 0.05         AS bin_end,
    COUNT(*)                                     AS policy_count
FROM vw_scored_population
WHERE score_decile = 1
  AND SmokerStatus = 'Smoker'
GROUP BY FLOOR(lapse_score * 20)
ORDER BY bin_start
;
