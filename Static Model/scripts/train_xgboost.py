"""Train an XGBoost model from Excel files in Static Model/Dataset.

This script builds a next-hour GHI regressor using chronological features,
lagged weather context, and rolling-window statistics.

Refactored into modular components:
- config: CLI arguments and configuration
- data_loader: Excel file loading and API integration
- features: Feature engineering
- model: Model training and evaluation
- artifacts: Output saving
- logging_config: Logging setup
"""

from __future__ import annotations

import logging

import pandas as pd

from config import parse_args
from data_loader import load_api_test_dataset, load_dataset
from features import prepare_features
from logging_config import configure_logging
from model import rolling_backtest, train_and_evaluate, train_and_evaluate_explicit_split
from artifacts import save_artifacts, save_rolling_backtest_artifacts




LOGGER = logging.getLogger("static_xgboost")


def main() -> None:
    """Run full training pipeline over the static Excel dataset."""
    configure_logging()
    args = parse_args()

    df = load_dataset(
        args.dataset_dir,
        max_rows_per_file=args.max_rows_per_file,
        max_files=args.max_files,
    )

    test_df: pd.DataFrame | None = None
    if args.backtest_mode == "holdout":
        if args.test_source == "api":
            test_df = load_api_test_dataset(
                city=args.api_city,
                test_year=args.test_year,
                api_start_date=args.api_start_date,
                api_end_date=args.api_end_date,
            )
        elif args.test_dataset_dir is not None:
            logger = logging.getLogger("static_xgboost")
            logger.info("Loading external test dataset: %s", args.test_dataset_dir)
            test_df = load_dataset(
                args.test_dataset_dir,
                max_rows_per_file=args.max_rows_per_file,
                max_files=args.max_files,
            )

    modes = ["ghi", "temperature"] if args.target_mode == "both" else [args.target_mode]
    for mode in modes:
        x, y, ts, _ = prepare_features(df, mode)
        if args.backtest_mode == "holdout":
            if test_df is not None:
                x_test_raw, y_test, _, _ = prepare_features(test_df, mode)

                # Align columns so train/test matrices are strictly compatible.
                missing_in_test = [c for c in x.columns if c not in x_test_raw.columns]
                for col in missing_in_test:
                    x_test_raw[col] = 0.0
                extra_in_test = [c for c in x_test_raw.columns if c not in x.columns]
                if extra_in_test:
                    x_test_raw = x_test_raw.drop(columns=extra_in_test)
                x_test = x_test_raw[x.columns]

                if args.test_source == "api":
                    test_descriptor = (
                        f"api:{args.api_city}:{args.api_start_date or args.test_year}"
                        f"->{args.api_end_date or args.test_year}"
                    )
                else:
                    test_descriptor = f"external_dataset:{args.test_dataset_dir}"

                model, metrics, pred_df = train_and_evaluate_explicit_split(
                    x_train=x,
                    y_train=y,
                    x_test=x_test,
                    y_test=y_test,
                    test_descriptor=test_descriptor,
                )
            else:
                model, metrics, pred_df = train_and_evaluate(
                    x=x,
                    y=y,
                    timestamps=ts,
                    test_year=args.test_year,
                )
            save_artifacts(
                model,
                metrics,
                pred_df,
                list(x.columns),
                args.artifacts_dir,
                target_mode=mode,
            )
            logger = logging.getLogger("static_xgboost")
            logger.info(
                "Training complete (%s) | MAE=%.4f RMSE=%.4f R2=%.4f",
                mode,
                metrics["mae"],
                metrics["rmse"],
                metrics["r2"],
            )
            continue

        total_rows = len(x)
        train_size = args.rolling_train_size if args.rolling_train_size > 0 else int(total_rows * 0.6)
        test_size = args.rolling_test_size if args.rolling_test_size > 0 else max(int(total_rows * 0.1), 500)
        step_size = args.rolling_step_size if args.rolling_step_size > 0 else test_size

        folds_df, summary = rolling_backtest(
            x=x,
            y=y,
            train_size=train_size,
            test_size=test_size,
            step_size=step_size,
            max_folds=args.rolling_max_folds,
        )
        save_rolling_backtest_artifacts(
            folds_df=folds_df,
            summary=summary,
            artifacts_dir=args.artifacts_dir,
            target_mode=mode,
        )
        logger = logging.getLogger("static_xgboost")
        logger.info(
            "Rolling backtest complete (%s) | folds=%d MAE=%.4f±%.4f RMSE=%.4f±%.4f R2=%.4f±%.4f",
            mode,
            summary["folds"],
            summary["mae_mean"],
            summary["mae_std"],
            summary["rmse_mean"],
            summary["rmse_std"],
            summary["r2_mean"],
            summary["r2_std"],
        )


if __name__ == "__main__":
    main()

