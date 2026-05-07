#pragma once

#include <QElapsedTimer>
#include <QTimer>
#include <QVariantMap>
#include <QVector>
#include <QWidget>

class FFTSpectrumWidget final : public QWidget {
    Q_OBJECT
public:
    explicit FFTSpectrumWidget(QWidget *parent = nullptr);
    ~FFTSpectrumWidget() override = default;

public slots:
    void set_frame(const QVariantMap &frame);
    void set_state(const QString &state);
    void set_analyzer_status(const QString &status);
    void set_bar_count(int count);

protected:
    void paintEvent(QPaintEvent *event) override;

private slots:
    void tick_render();

private:
    static double clamp01(double value);
    void resize_arrays(int count);
    void draw_grid(QPainter &p, const QRect &r);
    void draw_bars(QPainter &p, const QRect &r);
    void draw_vu(QPainter &p, const QRect &r, double value, double peak, const QString &label);
    QString fmt_time(double seconds) const;

    QVector<double> bars_;
    QVector<double> targets_;
    QVector<double> peaks_;
    int bar_count_ = 64;

    double vu_l_ = 0.0;
    double vu_r_ = 0.0;
    double vu_peak_l_ = 0.0;
    double vu_peak_r_ = 0.0;
    double decode_pos_ = 0.0;
    double mpv_pos_ = 0.0;
    double sync_delta_ = 0.0;
    double fft_ms_ = 0.0;
    double analyzer_fps_ = 0.0;
    double paint_ms_ = 0.0;
    double stale_ms_ = 0.0;
    quint64 frames_ = 0;
    bool stream_ = false;

    QString state_ = QStringLiteral("idle");
    QString status_ = QStringLiteral("NATIVE C++ FFT WIDGET READY");
    QString backend_ = QStringLiteral("native");

    QElapsedTimer clock_;
    qint64 last_frame_ms_ = 0;
    QTimer render_timer_;
};
