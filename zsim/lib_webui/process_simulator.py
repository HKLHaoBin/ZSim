import json
from typing import Any, Iterator

import polars as pl
import streamlit as st
from define import CONFIG_PATH
from lib_webui.process_apl_editor import APLArchive, APLJudgeTool

from zsim.simulator.config_classes import (
    AttrCurveConfig,
    WeaponConfig,
)
from zsim.simulator.config_classes import (
    SimulationConfig as SimCfg,
)

from .constants import stats_trans_mapping


def generate_parallel_args(
    stop_tick: int,
    parallel_cfg: dict,
    run_turn_uuid: str,
) -> Iterator[SimCfg]:
    """生成用于并行模拟的参数。

    Args:
        stop_tick: 模拟停止的 tick 数。
        parallel_cfg: 并行模式的配置字典。
        run_turn_uuid: 当前运行轮次的 UUID。

    Yields:
        MainArgs: 为每个模拟任务生成的参数对象。
    """
    # Determine the function based on enabled flags
    func = None
    if parallel_cfg.get("adjust_sc", {}).get("enabled", False):
        func = "attr_curve"
    elif parallel_cfg.get("adjust_weapon", {}).get("enabled", False):
        func = "weapon"

    if func == "attr_curve":
        adjust_sc_cfg = parallel_cfg["adjust_sc"]
        sc_list = adjust_sc_cfg["sc_list"]
        sc_range_start, sc_range_end = adjust_sc_cfg["sc_range"]
        remove_equip_list = adjust_sc_cfg.get(
            "remove_equip_list", []
        )  # 获取需要移除装备的词条列表，如果不存在则为空列表
        for sc_name in sc_list:
            for sc_value in range(sc_range_start, sc_range_end + 1):
                args = AttrCurveConfig(
                    stop_tick=stop_tick,
                    mode="parallel",
                    func=func,
                    adjust_char=parallel_cfg["adjust_char"],
                    sc_name=stats_trans_mapping[sc_name],
                    sc_value=sc_value,
                    run_turn_uuid=run_turn_uuid,
                    remove_equip=sc_name in remove_equip_list,
                )
                yield args
    elif func == "weapon":
        adjust_weapon_cfg = parallel_cfg["adjust_weapon"]
        weapon_list = adjust_weapon_cfg["weapon_list"]
        for weapon in weapon_list:
            args = WeaponConfig(
                stop_tick=stop_tick,
                mode="parallel",
                func=func,
                adjust_char=parallel_cfg["adjust_char"],
                weapon_name=weapon["name"],
                weapon_level=weapon["level"],
                run_turn_uuid=run_turn_uuid,
            )
            yield args
    else:
        raise ValueError(f"Unknown func: {func}, full cfg: {parallel_cfg}")


def apl_selecter():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        default_apl_path = config["database"]["APL_FILE_PATH"]

    apl_archive = APLArchive()
    default_apl_titile = apl_archive.get_title_from_path(default_apl_path)
    options_list = list(apl_archive.options or [])
    # 检查 default_apl_titile 是否在选项列表中
    if default_apl_titile in options_list:
        default_index = options_list.index(default_apl_titile)
    else:
        default_index = 0  # 如果不在，则默认选择第一个选项

    selected_title = st.selectbox(
        "APL选项",
        options_list,
        label_visibility="collapsed",
        index=default_index,
    )
    return selected_title


def save_apl_selection(selected_title: str):
    """保存APL选择。

    Args:
        selected_title: 选中的APL标题。
    """
    apl_archive = APLArchive()
    original_path = apl_archive.get_origin_relative_path(selected_title)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["database"]["APL_FILE_PATH"] = original_path
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def get_default_apl_tile() -> str | None:
    """获取默认APL的标题。

    Returns:
        str: 默认APL的标题。
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        default_apl_path = config["database"]["APL_FILE_PATH"]

    apl_archive = APLArchive()
    return apl_archive.get_title_from_path(default_apl_path)


def show_apl_judge_result(selected_title: str | None = None) -> bool:
    """显示并返回判断结果APL的判断结果。

    Args:
        selected_title (str): 选中的APL标题。

    Returns:
        bool: 判断结果APL的判断结果。
    """
    if selected_title is None:
        selected_title = get_default_apl_tile()
    if selected_title is None:
        st.error("未找到默认APL，请先选择一个APL。")
        return False
    apl_archive = APLArchive()
    apl_data: dict[str, Any] | None = apl_archive.get_apl_data(selected_title)
    if apl_data is None:
        st.error("未找到APL数据，请检查APL文件是否正确。")
        return False
    apl_judge_tool = APLJudgeTool(apl_data)
    required_chars_result: tuple[bool, list[str]] = (
        apl_judge_tool.judge_requried_chars()
    )
    option_result_result: tuple[bool, list[str]] = apl_judge_tool.judge_optional_chars()
    char_config_result: tuple[bool, dict[str, str | int]] = (
        apl_judge_tool.judge_char_config()
    )
    # 新增：获取所有必选和可选角色名
    all_required = apl_judge_tool.required_chars
    all_optional = apl_judge_tool.optional_chars
    # 获取已满足的必选和可选角色名
    satisfied_required = [c for c in all_required if c not in required_chars_result[1]]
    satisfied_optional = [c for c in all_optional if c not in option_result_result[1]]
    if required_chars_result[0]:
        st.success(f"必选角色满足要求：{satisfied_required}")
    else:
        st.error(f"必选角色缺少：{required_chars_result[1]}")
    if option_result_result[0]:
        st.success(f"可选角色满足要求：{satisfied_optional}")
    else:
        st.error(f"可选角色缺少：{option_result_result[1]}")
    if char_config_result[0]:
        st.success("角色配置满足要求")
    else:
        st.error(f"角色配置缺少：{char_config_result[1]}")
    return required_chars_result[0] and char_config_result[0]


def enemy_selector() -> tuple[int, int]:
    """敌人配置选择器。

    Returns:
        tuple[int, int]: (index_ID, adjust_ID) 元组
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        current_index = config["enemy"]["index_ID"]
        current_adjust = config["enemy"]["adjust_ID"]

    # 从enemy.csv获取所有唯一的IndexID
    enemy_df = pl.scan_csv("zsim/data/enemy.csv")
    index_options: list[int] = sorted(
        enemy_df.select("IndexID").unique().collect().to_series().to_list()
    )

    # 从enemy_adjustment.csv获取所有唯一的ID
    adjust_df = pl.scan_csv("zsim/data/enemy_adjustment.csv")
    adjust_options: list[int] = sorted(
        adjust_df.select("ID").unique().collect().to_series().to_list()
    )

    # 创建两列布局
    col1, col2 = st.columns(2)

    with col1:
        selected_index = st.selectbox(
            "敌人IndexID",
            index_options,
            index=index_options.index(current_index)
            if current_index in index_options
            else 0,
        )

    with col2:
        selected_adjust = st.selectbox(
            "敌人属性调整ID",
            adjust_options,
            index=adjust_options.index(current_adjust)
            if current_adjust in adjust_options
            else 0,
        )

    return selected_index, selected_adjust


def save_enemy_selection(index_id: int, adjust_id: int):
    """保存敌人配置选择。

    Args:
        index_id: 选中的敌人基础ID
        adjust_id: 选中的敌人调整ID
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    config["enemy"]["index_ID"] = index_id
    config["enemy"]["adjust_ID"] = adjust_id

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
