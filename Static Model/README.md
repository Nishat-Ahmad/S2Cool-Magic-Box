# Static Model - XGBoost Next-Hour Weather Forecasting

Modular training pipeline for next-hour GHI and temperature forecasting using XGBoost regressors trained on historical Excel weather datasets and validated on real-time API data.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Train both models with local data (holdout evaluation)
python scripts/train_xgboost.py --target-mode both --backtest-mode holdout

# Train with API-based test data (2026 Islamabad)
python scripts/train_xgboost.py --target-mode both --test-source api --api-city Islamabad \
  --api-start-date 2026-01-01 --api-end-date 2026-03-01

# Rolling-window backtest
python scripts/train_xgboost.py --target-mode ghi --backtest-mode rolling
```

## Project Structure

### Scripts (refactored modular architecture)

- **scripts/train_xgboost.py** — Main orchestration script (~60 lines)
- **scripts/config.py** — CLI argument parsing & configuration
- **scripts/data_loader.py** — Excel file ingestion & Open-Meteo API integration
- **scripts/features.py** — Feature engineering (lags, cyclical, rolling statistics)
- **scripts/model.py** — XGBoost training & evaluation (holdout, rolling backtest)
- **scripts/artifacts.py** — Model, metrics, and predictions output saving
- **scripts/logging_config.py** — Logging configuration
- **scripts/__init__.py** — Package marker

### Data & Artifacts

- **dataset/** — Input Excel weather files (79/80 usable files)
- **artifacts/** — Output models, metrics, predictions, and feature importance
- **logs/** — Training run logs

## Detailed Implementation

### 1. Data Loading Strategy


**Location:** `scripts/features.py`

- **Calendar features:** hour, day_of_year, month
- **Cyclical encoding:**
  - hour_sin, hour_cos (24-hour cycle)
  - doy_sin, doy_cos (365.25-day solar year cycle)
- **Lag features:** ghi_lag_1, ghi_lag_2, ghi_lag_3, ghi_lag_24, temp_lag_1
- **Rolling statistics:** ghi_rolling_mean_3h, ghi_rolling_std_3h (3-hour windows)
- **Targets:** target_ghi_next_1h, target_temperature_next_1h (shifted by -1 hour)
- Handles missing values via interpolation and forward/backward fill

### 3. Model Training & Evaluation

**Location:** `scripts/model.py`

- **XGBoost configuration:**
  - 500 estimators, max_depth=6, learning_rate=0.05
  - Subsample=0.9, colsample_bytree=0.9, random_state=42
- **Evaluation modes:**
  - Holdout: chronological train/test split (year-based or 80/20)
  - Rolling backtest: fixed-window folds with configurable train/test/step sizes
- **Explicit split support:** For external test datasets (e.g., API or test-year holdout)
- **Metrics:** MAE, RMSE, R²

### 4. Artifact Management

**Location:** `scripts/artifacts.py`

- Model joblib serialization
- Metrics JSON (includes feature list, test descriptor, performance scores)
- Test predictions CSV (actual/predicted/residual)
- Feature importance CSV (sorted by importance score)
- Rolling backtest: per-fold metrics + aggregated summary statistics

## Command-Line Interface

**Main script:** `scripts/train_xgboost.py`

### Core arguments

- `--dataset-dir` (Path, default: `dataset`) — Folder containing .xlsx files
- `--artifacts-dir` (Path, default: `artifacts`) — Output folder for models/metrics
- `--target-mode` (ghi | temperature | both) — Prediction target
- `--backtest-mode` (holdout | rolling) — Evaluation strategy

### Data loading options

- `--max-rows-per-file` (int, default: 20000) — Cap rows per file (0 = no cap)
- `--max-files` (int, default: 0) — Limit number of files (0 = all files)

### Holdout evaluation options

- `--test-year` (int, default: 2026) — Calendar year for test set (chronological split)
- `--test-source` (dataset | api, default: dataset)
  - `dataset`: Use local dataset directory for test data
  - `api`: Fetch test data from Open-Meteo API
- `--test-dataset-dir` (Path) — External test dataset directory
- `--api-city` (Islamabad | Lahore | Karachi | Peshawar, default: Islamabad)
- `--api-start-date` (YYYY-MM-DD) — API test period start
- `--api-end-date` (YYYY-MM-DD) — API test period end

### Rolling backtest options

- `--rolling-train-size` (int, default: 0) — Training window (0 = 60% of data)
- `--rolling-test-size` (int, default: 0) — Test window (0 = 10% or 500 rows)
- `--rolling-step-size` (int, default: 0) — Step between folds (0 = test_size)
- `--rolling-max-folds` (int, default: 5) — Maximum folds to evaluate

## Artifact outputs


**Files generated in `artifacts/`:**

- `xgboost_ghi_model.joblib` — Trained GHI forecasting model
- `xgboost_ghi_metrics.json` — Performance metrics & metadata (train/test rows, MAE, RMSE, R²)
- `xgboost_ghi_test_predictions.csv` — Holdout actual/predicted/residual values
- `xgboost_ghi_feature_importance.csv` — Feature importance scores (sorted)
- `xgboost_temp_model.joblib` — Trained temperature forecasting model
- `xgboost_temp_metrics.json` — Temperature model metrics & metadata
- `xgboost_temp_test_predictions.csv` — Temperature predictions
- `xgboost_temp_feature_importance.csv` — Temperature model feature importance
- `xgboost_*_rolling_backtest_folds.csv` — Per-fold metrics (if rolling mode)
- `xgboost_*_rolling_backtest_summary.json` — Aggregated backtest statistics

## Training metrics & validation results

Run command:

```powershell
C:\Users\Droid\AppData\Local\Python\pythoncore-3.14-64\python.exe "d:/Code/S2Cool-Magic-Box/Static Model/train_xgboost.py" --target-mode both --max-rows-per-file 0 --max-files 0
```

Run summary:

- Files scanned: 80
- Usable files: 79
- Skipped files: 1
- Total rows loaded: 608006

GHI model metrics:

- train_rows: 346113
- test_rows: 86529
- MAE: 17.1705728591
- RMSE: 44.9622737444
- R2: 0.9752908990

Temperature model metrics:

- train_rows: 346113
- test_rows: 86529
- MAE: 0.2810751686
- RMSE: 0.5017530721
- R2: 0.9963254656

## Remaining known issue

- One dataset file is structurally invalid and still skipped:
  - Static Model/Dataset/Pk-Isb_2020-01-Mar-to-15-Dec.xlsx
  - Reason: not a valid zip-based xlsx container.

## Current status

- The pipeline now ingests nearly all files in this dataset automatically.
- Artifacts are generated successfully.
- The script is ready for larger/full-row runs by setting --max-rows-per-file 0.

## Recent temperature mode validation

Run command:

```powershell
C:\Users\Droid\AppData\Local\Python\pythoncore-3.14-64\python.exe "d:/Code/S2Cool-Magic-Box/Static Model/train_xgboost.py" --target-mode temperature --max-rows-per-file 1000 --max-files 20
```

Latest temp metrics:

- train_rows: 8912
- test_rows: 2228
- MAE: 0.2982
- RMSE: 0.6787
- R2: 0.9818

## API-based holdout evaluation on 2026 Islamabad data

Run command:

```powershell
py -3.14 "scripts/train_xgboost.py" --dataset-dir "dataset" --target-mode "both" --backtest-mode "holdout" --test-source "api" --api-city "Islamabad" --api-start-date "2026-01-01" --api-end-date "2026-03-01" --max-rows-per-file 1500 --artifacts-dir "artifacts"
```

Execution summary:

- Dataset source: local Excel files (79/80 usable files)
- Dataset rows loaded: 28,368 (capped at max-rows-per-file=1500)
- Test data source: Open-Meteo API, Islamabad, 2026-01-01 to 2026-03-01
- Test rows fetched: 1,440 hourly records, processed to 1,439 (after feature engineering)

**GHI model results:**

- train_rows: 26,846
- test_rows: 1,439
- test_descriptor: api:Islamabad:2026-01-01->2026-03-01
- MAE: 56.4147
- RMSE: 86.2981
- R2: 0.8278

**Temperature model results:**

- train_rows: 26,846
- test_rows: 1,439
- test_descriptor: api:Islamabad:2026-01-01->2026-03-01
- MAE: 1.1252
- RMSE: 1.5487
- R2: 0.9078

This run demonstrates the model's ability to forecast next-hour conditions on external, real-world 2026 weather data from an API source, validating generalization performance beyond the static training dataset.

## Latest rolling backtest validation (April 6, 2026)

Run command:

```powershell
python scripts/train_xgboost.py --dataset-dir "..\dataset" --artifacts-dir "..\artifacts" --target-mode both --backtest-mode rolling
```

Execution summary:

- Dataset source: local Excel files (79/80 usable files, "Pk-Isb_2020-01-Mar-to-15-Dec.xlsx" skipped as invalid)
- Total dataset rows loaded: 195,076 (capped at max-rows-per-file=20000)
- Rows after feature engineering: 191,838
- Validation strategy: 4-fold rolling-window backtest
- Train/test window sizes: 115,102 training rows per fold, 19,183 test rows per fold

**GHI (Global Horizontal Irradiance) model results:**

- MAE: 15.7696 ± 6.3132 W/m²
- RMSE: 41.0250 ± 13.9539 W/m²
- R²: 0.9779 ± 0.0101
- Artifacts: `xgboost_ghi_rolling_backtest_folds.csv`, `xgboost_ghi_rolling_backtest_summary.json`

**Temperature model results:**

- MAE: 0.2567 ± 0.0614 °C
- RMSE: 0.4595 ± 0.1303 °C
- R²: 0.9949 ± 0.0020
- Artifacts: `xgboost_temp_rolling_backtest_folds.csv`, `xgboost_temp_rolling_backtest_summary.json`

This rolling backtest demonstrates consistent model performance across sequential time windows, validating chronological stability of the forecasting models.
