from flask import Blueprint, jsonify


bp = Blueprint("time_api", __name__)


@bp.route("/time-info", methods=["GET"])
def time_info():
    """
    网关时间工具：返回当前北京时间的日期、星期、时间段、具体时间和农历信息。
    供渡在工具调用里使用，不依赖前端自己的时间插件。
    """
    from utils.time_aware import (
        get_date_only,
        get_weekday_cn,
        get_time_period,
        get_exact_time,
        get_lunar_and_terms,
        now_beijing_iso,
    )

    iso = now_beijing_iso()
    date = get_date_only()
    weekday = get_weekday_cn()
    period = get_time_period()
    hm = get_exact_time()
    lunar = get_lunar_and_terms()
    return jsonify(
        {
            "iso": iso,
            "date": date,
            "weekday_cn": weekday,
            "time_hm": hm,
            "period": period,
            "lunar": lunar,
        }
    )


@bp.route("/time-now", methods=["GET"])
def time_now():
    """
    极简时间工具：只返回当前北京时间的 HH:mm，供 get_time_info 工具直接使用。
    """
    from utils.time_aware import get_exact_time

    hm = get_exact_time()
    return jsonify({"time_hm": hm})
